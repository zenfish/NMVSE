
Interpret midi sounds coming from the NMVSE
====

I picked up the [NMVSE](https://thisisnoiseinc.com/products/nmsve-order), a cool lil' midi controller @ [Amazon](https://www.amazon.com/NMSVE-this-NOISE-inc-controller/dp/B0CXF6QNY2) the other day.

While it can be used with Logic Pro, Kontakt, etc., I thought I'd try my hand at writing my own. I started off writing the basics doing connectivity and playing notes, then fed the script iteratively through Claude 4 Sonnet to get the resulting program, which is python terminal/command line program.

Works on a M1 Mac running Sequoia/macOS 15.5 (24F74), but it should work on most modern macs/whatever... if it doesn't work on something, let me know!

Requires python3 and some supporting libraries (``pip3 install -r requirements`` or w/e should get them installed.)

Getting it running
====

*** You need to have the NMVSE already connected prior to starting (if anyone knows a reasonable way to auto-connect, feel free to drop me a line.)

Some options -

```bash
./noize.py  --help
usage: noize.py [-h] [-a] [-b ARP_BPM] [-c] [-r ARP_RATE] [-d {up,down,random}] [--arp-overlay] [--arp-latch] [-n] [-na ARP_PATTERN_N] [-p ARP_PATTERN] [-f SOUND_FONT_FILE] [-i INSTRUMENT] [-k KEY]
                [-l {3,2,1,0,errors-only,info,verbose,debug}] [-s SCALE] [--only-scale-permitted]

options:

  -h, --help            show this help message and exit
  -c, --chords          Play chords
  -f SOUND_FONT_FILE, --sound-font-file SOUND_FONT_FILE     give a full path to an alternate SF2 file
  -i INSTRUMENT, --instrument INSTRUMENT - the instrument number or name to use
  -k KEY, --key KEY     Key to play in (e.g., "C", "F#", "Bb"). Default is C
  -l {3,2,1,0,errors-only,info,verbose,debug}, --log-level {3,2,1,0,errors-only,info,verbose,debug}    - Logging level (0/errors-only, 1/debug, 2/verbose, 3/info)
  -n, --notes           Play notes instead of chords
  -s SCALE, --scale SCALE   - scale to use (e.g., "C-D-E-F-G-A-B" or predefined scale name)
  --only-scale-permitted    - only play/allow notes that are in the specified scale

# arp stuff

  -a, --arp             Enable arpeggiation
  -b ARP_BPM, --arp-bpm ARP_BPM       -  Beats per minute for arpeggiation (default: 120)
  -r ARP_RATE, --arp-rate ARP_RATE    -  Rate of notes per beat as a fraction (e.g., "1/4", "1/8"). Default is 1/4.
  -d {up,down,random}, --arp-direction {up,down,random}  - Direction of arpeggiation (default: up)
  --arp-overlay         Continue playing arpeggio after key release, allowing multiple arps to overlap
  --arp-latch           Stop previous arp sounds when starting a new sequence
  -na ARP_PATTERN_N, --arp-pattern-n    ARP_PATTERN_N - Number of beats in arp pattern (default: 4)
  -p ARP_PATTERN,    --arp-pattern      ARP_PATTERN - pattern for arpeggiation (e.g., "+3.+1...-1.+2+3" or "increment", "odd", "even")

```
Just running it with no options will try to connect with the defaults (plays chords with piano-ish sounds.)

Controls -
====
Here's a rough ASCII NMVSE of the thing -

```
+-------------------------+
|  .                      |
| / \    .... slider .... |
| \./                     |
|                         |
| b1 b2 b3 b4             |
| b5 b2 b3 b4             |
| b9 bA bB bC             |
|                         |
+-------------------------+
```
When the grid of buttons (b1-bC (hex ;)) is pressed it'll play chords on the piano (sic) from C -> C on the next octave.

I wasn't sure what to do with the knob, so for now it controls volume/gain.

The default octave depends on where the slider on the NMVSE is (right is a higher octave.) Mine goes from the 2nd to 8th octaves.

So many options to beat with sticks
=====

Some of the big ones -

``-n/--notes`` will play single notes instead of a chord.

``-k/--key`` select whatever key you want.

``-s/--scale`` select the scale - using "-s help" will dump out the known scales. You can define your own by simply using notes separated by "-" - e.g. "C-D-E-F-G-A-B" or w/e.

Lots of arpeggiator options... it runs in an event loop waiting for something to happen (an opportunity to play with the python's async capabilities.) You can set the rate, the pattern, the direction, etc, etc. The random option is random, but for now only random the first time and then will repeat the same random pattern.

``--arp-latch`` lets the arpeggios remain playing after you release the button.
``--arp-overlay`` is perhaps useless, but it allows multiple arpeggios going in unison.

``-p/--arp-pattern`` let's you select increment, odd, even, or define your own patterns. Patterns are either a "." (a rest) or a plus/minus sign ("+"/"-") followed by a digit ("-0"/"+0" are identical), indicating the number of semitones away from root of the key. So "+3.+1...-1" would be +3 semitones up from the root, a rest, +1 up, three more rests, and a final note 1 semitone down.

``-r/--arp-rate`` sets the rate of notes per beat as a fraction (e.g., "1/4", "1/8"). Default is 1/4.


