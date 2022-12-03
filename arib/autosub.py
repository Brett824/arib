#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: set ts=2 expandtab:
'''
Module: autosub.py
Desc: Extract CCs from .ts file-->translate via bing-->output .ass subtitle file
Author: John O'Neil
Email: oneil.john@gmail.com
DATE: Thursday, May 29th 2014

Stab at simple auto subtitling japanese programs via their Closed captions
embedded in MPEG Transport Stream data.
  
'''
from bing import translate
import code_set as code_set
import control_characters as control_characters
import codecs
import re

import os
import argparse
import copy
from data_group import next_data_group
from closed_caption import next_data_unit
from closed_caption import StatementBody
import code_set as code_set
import control_characters as control_characters
from ts import next_ts_packet
from ts import next_pes_packet
from ts import PESPacket
from data_group import DataGroup
from secret_key import SECRET_KEY
from secret_key import CLIENT_ID


class Pos(object):
    '''Screen position in pixels
    '''

    def __init__(self, x, y):
        self._x = x
        self._y = y

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y


class Size(object):
    '''Screen width, height of an area in pixels
    '''

    def __init__(self, w, h):
        self._w = w
        self._h = h

    @property
    def width(self):
        return self._w

    @property
    def height(self):
        return self._h


class ClosedCaptionArea(object):
    def __init__(self):
        self._UL = Pos(170, 30)
        self._Dimensions = Size(620, 480)
        self._CharacterDim = Size(36, 36)
        self._char_spacing = 4
        self._line_spacing = 24

    @property
    def UL(self):
        return self._UL

    @property
    def Dimensions(self):
        return self._Dimensions

    def RowCol2ScreenPos(self, row, col):
        return Pos(self.UL.x + col * (self._CharacterDim.width + self._char_spacing),
                   self.UL.y + row * (self._CharacterDim.height + self._line_spacing))


class ASSFile(object):
    '''Wrapper for a single open utf-8 encoded .ass subtitle file
    '''

    def __init__(self, filepath):
        self._f = codecs.open(filepath, 'w', encoding='utf8')

    def __del__(self):
        if self._f:
            self._f.close()

    def write(self, line):
        '''Write indicated string to file. usually a line of dialog.
        '''
        self._f.write(line)

    def write_header(self, width, height, title):
        header = '''[Script Info]
; Script generated by ts2ass script
Title: Default Aegisub file
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
Video Aspect Ratio: 0
Video Zoom: 1
Video Position: 0
Last Style Storage: Default
Video File: {title}


'''.format(width=width, height=height, title=title)
        self._f.write(header)

    def write_styles(self):
        styles = '''[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: normal,MS UI Gothic,37,&H00FFFFFF,&H000000FF,&H00000000,&H88000000,0,0,0,0,100,100,0,0,1,2,2,1,10,10,10,0
Style: medium,MS UI Gothic,37,&H00FFFFFF,&H000000FF,&H00000000,&H88000000,0,0,0,0,50,100,0,0,1,2,2,1,10,10,10,0
Style: small,MS UI Gothic,18,&H00FFFFFF,&H000000FF,&H00000000,&H88000000,0,0,0,0,100,100,0,0,1,2,2,1,10,10,10,0


'''
        self._f.write(styles)


def asstime(seconds):
    '''format floating point seconds elapsed time to 0:02:14.53
    '''
    days = int(seconds / 86400)
    seconds -= 86400 * days
    hrs = int(seconds / 3600)
    seconds -= 3600 * hrs
    mins = int(seconds / 60)
    seconds -= 60 * mins
    return '{h:01d}:{m:02d}:{s:02.2f}'.format(h=hrs, m=mins, s=seconds)


def kanji(formatter, k, timestamp):
    # ignore all 'small' styled characters as they're prob furigana
    if formatter._current_style != 'small':
        formatter._current_lines[-1] += str(k)


def alphanumeric(formatter, a, timestamp):
    if formatter._current_style != 'small':
        formatter._current_lines[-1] += str(a)


def hiragana(formatter, h, timestamp):
    if formatter._current_style != 'small':
        formatter._current_lines[-1] += str(h)


def katakana(formatter, k, timestamp):
    if formatter._current_style != 'small':
        formatter._current_lines[-1] += str(k)


def medium(formatter, k, timestamp):
    # formatter._current_lines[-1] += u'{\\rmedium}' + formatter._current_color
    formatter._current_style = 'medium'


def normal(formatter, k, timestamp):
    # formatter._current_lines[-1] += u'{\\rnormal}' + formatter._current_color
    formatter._current_style = 'normal'


def small(formatter, k, timestamp):
    # formatter._current_lines[-1] += u'{\\rsmall}' + formatter._current_color
    formatter._current_style = 'small'


def space(formatter, k, timestamp):
    formatter._current_lines[-1] += ' '


def drcs(formatter, c, timestamp):
    formatter._current_lines[-1] += str(c)


def black(formatter, k, timestamp):
    # {\c&H000000&} \c&H<bb><gg><rr>& {\c&Hffffff&}
    formatter._current_lines[-1] += '{\c&H000000&}'
    formatter._current_color = '{\c&H000000&}'


def red(formatter, k, timestamp):
    # {\c&H0000ff&}
    formatter._current_lines[-1] += '{\c&H0000ff&}'
    formatter._current_color = '{\c&H0000ff&}'


def green(formatter, k, timestamp):
    # {\c&H00ff00&}
    formatter._current_lines[-1] += '{\c&H00ff00&}'
    formatter._current_color = '{\c&H00ff00&}'


def yellow(formatter, k, timestamp):
    # {\c&H00ffff&}
    formatter._current_lines[-1] += '{\c&H00ffff&}'
    formatter._current_color = '{\c&H00ffff&}'


def blue(formatter, k, timestamp):
    # {\c&Hff0000&}
    formatter._current_lines[-1] += '{\c&Hff0000&}'
    formatter._current_color = '{\c&Hff0000&}'


def magenta(formatter, k, timestamp):
    # {\c&Hff00ff&}
    formatter._current_lines[-1] += '{\c&Hff00ff&}'
    formatter._current_color = '{\c&Hff00ff&}'


def cyan(formatter, k, timestamp):
    # {\c&Hffff00&}
    formatter._current_lines[-1] += '{\c&Hffff00&}'
    formatter._current_color = '{\c&Hffff00&}'


def white(formatter, k, timestamp):
    # {\c&Hffffff&}
    formatter._current_lines[-1] += '{\c&Hffffff&}'
    formatter._current_color = '{\c&Hffffff&}'


def position_set(formatter, p, timestamp):
    '''Active Position set coordinates are given in character row, colum
    So we have to calculate pixel coordinates (and then sale them)
    '''
    pos = formatter._CCArea.RowCol2ScreenPos(p.row, p.col)
    # line = u'{{\\r{style}}}{color}{{\pos({x},{y})}}'.format(color=formatter._current_color, style=formatter._current_style, x=pos.x, y=pos.y)
    line = '{{\\r{style}}}{color}{{\pos({x},{y})}}'.format(color=formatter._current_color,
                                                            style=formatter._current_style, x=pos.x, y=pos.y)
    # formatter._current_lines.append(line)


a_regex = r'<CS:"(?P<x>\d{1,4});(?P<y>\d{1,4}) a">'


def control_character(formatter, csi, timestamp):
    '''This will be the most difficult to format, since the same class here
    can represent so many different commands.
    e.g:
    <CS:"7 S"><CS:"170;30 _"><CS:"620;480 V"><CS:"36;36 W"><CS:"4 X"><CS:"24 Y"><Small Text><CS:"170;389 a">
    '''
    cmd = str(csi)
    a_match = re.search(a_regex, cmd)
    if a_match:
        x = a_match.group('x')
        y = a_match.group('y')
        # formatter._current_lines.append(u'{{\\r{style}}}{color}{{\pos({x},{y})}}'.format(color=formatter._current_color, style=formatter._current_style, x=x, y=y))
        return


pos_regex = r'({\\pos\(\d{1,4},\d{1,4}\)})'


def clear_screen(formatter, cs, timestamp):
    start_time = asstime(formatter._elapsed_time_s)
    end_time = asstime(timestamp)

    if (len(formatter._current_lines[0]) or len(formatter._current_lines)) and start_time != end_time:
        for l in formatter._current_lines:
            if not len(l):
                continue
            eng = translate(l, client_id=CLIENT_ID, secret_key=SECRET_KEY)
            print(eng)
            line = 'Dialogue: 0,{start_time},{end_time},normal,,0000,0000,0000,,{line}\\N\n'.format(
                start_time=start_time, end_time=end_time, line=eng)
            # TODO: add option to dump to stdout
            # print line.encode('utf-8')
            formatter._ass_file.write(line)
            formatter._current_lines = ['']

    formatter._elapsed_time_s = timestamp


class ASSFormatter(object):
    '''
    Format ARIB objects to dialog of the sort below:
    Dialogue: 0,0:02:24.54,0:02:30.55,small,,0000,0000,0000,,{\pos(500,900)}ゴッド\N
    Dialogue: 0,0:02:24.54,0:02:30.55,small,,0000,0000,0000,,{\pos(780,900)}ほかく\N
    Dialogue: 0,0:02:24.54,0:02:30.55,normal,,0000,0000,0000,,{\pos(420,1020)}ＧＯＤの捕獲を目指す・\N
    '''

    DISPLAYED_CC_STATEMENTS = {
        code_set.Kanji: kanji,
        code_set.Alphanumeric: alphanumeric,
        code_set.Hiragana: hiragana,
        code_set.Katakana: katakana,
        control_characters.APS: position_set,  # {\pos(<X>,<Y>)}
        control_characters.MSZ: medium,  # {\rmedium}
        control_characters.NSZ: normal,  # {\rnormal}
        control_characters.SP: space,  # ' '
        control_characters.SSZ: small,  # {\rsmall}
        control_characters.CS: clear_screen,
        control_characters.CSI: control_character,  # {\pos(<X>,<Y>)}
        # control_characters.COL,
        # control_characters.BKF : black,
        # control_characters.RDF : red,
        # control_characters.GRF : green,
        # control_characters.YLF : yellow,
        # control_characters.BLF : blue,
        # control_characters.MGF : magenta,
        # control_characters.CNF : cyan,
        # control_characters.WHF : white,

        # largely unhandled DRCS just replaces them with unicode unknown character square
        code_set.DRCS0: drcs,
        code_set.DRCS1: drcs,
        code_set.DRCS2: drcs,
        code_set.DRCS3: drcs,
        code_set.DRCS4: drcs,
        code_set.DRCS5: drcs,
        code_set.DRCS6: drcs,
        code_set.DRCS7: drcs,
        code_set.DRCS8: drcs,
        code_set.DRCS9: drcs,
        code_set.DRCS10: drcs,
        code_set.DRCS11: drcs,
        code_set.DRCS12: drcs,
        code_set.DRCS13: drcs,
        code_set.DRCS14: drcs,
        code_set.DRCS15: drcs,

    }

    def __init__(self, ass_file=None, width=960, height=540, video_filename='unknown'):
        '''
        :param width: width of target screen in pixels
        :param height: height of target screen in pixels
        :param format_callback: callback method of form <None>callback(string) that
        can be used to dump strings to file upon each subsequent "clear screen" command.
        '''
        self._color = 'white'
        self._CCArea = ClosedCaptionArea()
        self._pos = Pos(0, 0)
        self._elapsed_time_s = 0.0
        self._ass_file = ass_file or ASSFile('./output.ass')
        self._ass_file.write_header(width, height, video_filename)
        self._ass_file.write_styles()
        self._current_lines = ['']
        self._current_style = 'normal'
        self._current_color = '{\c&Hffffff&}'

    def format(self, captions, timestamp):
        '''Format ARIB closed caption info tinto text for an .ASS file
        '''
        # TODO: Show progress in some way
        # print('File elapsed time seconds: {s}'.format(s=timestamp))
        # line = u'{t}: {l}\n'.format(t=timestamp, l=u''.join([unicode(s) for s in captions if type(s) in ASSFormatter.DISPLAYED_CC_STATEMENTS]))

        for c in captions:
            if type(c) in ASSFormatter.DISPLAYED_CC_STATEMENTS:
                # invoke the handler for this object type
                ASSFormatter.DISPLAYED_CC_STATEMENTS[type(c)](self, c, timestamp)
            else:
                # TODO: Warning of unhandled characters
                pass
                # print str(type(c))


def main():
    parser = argparse.ArgumentParser(description='Auto translate jp CCs in MPEG TS file.')
    parser.add_argument('infile', help='Input filename (MPEG2 Transport Stream File)', type=str)
    parser.add_argument('pid', help='Pid of closed caption ES to extract from stream.', type=int)
    # parser.add_argument('-k', '--secret_key', help='Windows secret key for bing translate API.', type=str, default='')
    args = parser.parse_args()

    pid = args.pid
    infilename = args.infile
    if not os.path.exists(infilename):
        print('Please provide input Transport Stream file.')
        os.exit(-1)

    # open an Ass file and formatter
    ass_file = ASSFile(infilename + '_ENG.ass')
    ass = ASSFormatter(ass_file)

    # CC data is not, in itself timestamped, so we've got to use packet info
    # to reconstruct the timing of the closed captions (i.e. how many seconds into
    # the file are they shown?)
    initial_timestamp = 0
    pes_packet = None
    pes = []
    elapsed_time_s = 0
    for packet in next_ts_packet(infilename):
        # always process timestamp info, regardless of PID
        if packet.adapatation_field() and packet.adapatation_field().PCR():
            current_timestamp = packet.adapatation_field().PCR()
            initial_timestamp = initial_timestamp or current_timestamp
            delta = current_timestamp - initial_timestamp
            elapsed_time_s = float(delta) / 90000.0

        # if this is the stream PID we're interestd in, reconstruct the ES
        if packet.pid() == pid:
            if packet.payload_start():
                pes = copy.deepcopy(packet.payload())
            else:
                pes.extend(packet.payload())
            pes_packet = PESPacket(pes)

            # if our packet is fully formed (payload all present) we can parse its contents
            if pes_packet.length() == (pes_packet.header_size() + pes_packet.payload_size()):

                data_group = DataGroup(pes_packet.payload())

                if not data_group.is_management_data():
                    # We now have a Data Group that contains caption data.
                    # We take out its payload, but this is further divided into 'Data Unit' structures
                    caption = data_group.payload()
                    # iterate through the Data Units in this payload via another generator.
                    for data_unit in next_data_unit(caption):
                        # we're only interested in those Data Units which are "statement body" to get CC data.
                        if not isinstance(data_unit.payload(), StatementBody):
                            continue

                        ass.format(data_unit.payload().payload(), elapsed_time_s)


if __name__ == "__main__":
    main()
