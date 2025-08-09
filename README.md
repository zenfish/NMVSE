
Interpret midi sounds coming from the NMVSE
====

I picked up the [NMVSE](https://thisisnoiseinc.com/products/nmsve-order), a cool lil' midi controller @ [Amazon](https://www.amazon.com/NMSVE-this-NOISE-inc-controller/dp/B0CXF6QNY2) the other day.

While it can be used with Logic Pro, Kontakt, etc., I thought I'd try my hand at writing my own. I started off writing the basics doing connectivity and playing notes, then fed the script iteratively through Claude 4 Sonnet to get the resulting program, which is python terminal/command line program.

Works on a M1 Mac running Sequoia/macOS 15.5 (24F74), but it should work on most modern macs/whatever... if it doesn't work on something, let me know!

- Requires python3 and some supporting libraries (``pip3 install -r requirements`` or w/e should get them installed.)

- It also requires fluidsynth to play sounds - on Macs you can install this with ``brew reinstall fluid-synth`` (you can go [here](https://brew.sh/) if you don't have brew to install that, it's pretty painless.)

- Finally, you need an sound font file (SF2 file)... I've included a fine one - GeneralUser GS 2.0.2 - by [S. Christian Collins](https://schristiancollins.com/generaluser.php). Handily, the instruments/sounds in the SF2 file (piano, tuba, whatever) correspond to the instrument #'s in the MIDI spec.


Getting it running
====

*** You need to have the NMVSE already connected prior to starting (if anyone knows a reasonable way to auto-connect, feel free to drop me a line.)

Some options -

```bash
usage: noize.py [-h] [-a] [-b ARP_BPM] [-c] [-r ARP_RATE] [-d {up,down,random}] [--arp-overlay] [--arp-latch] [-n] [-na ARP_PATTERN_N] [-p ARP_PATTERN] [-f SOUND_FONT_FILE] [-i INSTRUMENT] [-k KEY] [-l {3,2,1,0,errors-only,info,verbose,debug}] [-s SCALE] [--only-scale-permitted]

options:

  -h/--help              show this help message and exit
  -c/--chords            Play chords
  -f/--sound-font-file   font.SF2   - a full path to an alternate SF2 file
  -i/--instrument        INSTRUMENT - the instrument number or name to use. Default is 0/piano
  -k/--key               KEY        - Key to play in (e.g., "C", "F#", "Bb"). Default is C
  -n/--notes             Play notes instead of chords
  -s/--scale SCALE       Scale to use (e.g., "C-D-E-F-G-A-B" or predefined scale name)
  --only-scale-permitted - only play/allow notes that are in the specified scale
  -l/--log-level        {errors-only,info,verbose,debug,10,20,30,40}

# arp stuff

  -a/--arp                 Enable arpeggiation
  -b/--arp-bpm ARP_BPM     Beats per minute for arpeggiation (default: 120)
  -r/--arp-rate ARP_RATE   Rate of notes per beat as a fraction (e.g., "1/4", "1/8"). Default is 1/4.
  -d/--arp-direction       {up,down,random}  - Direction of arpeggiation (default: up)
  --arp-overlay            Continue playing arpeggio after key release, allowing multiple arps to overlap
  --arp-latch              Stop previous arp sounds when starting a new sequence
  -na/--arp-pattern-n ARP_PATTERN_N - Number of beats in arp pattern (default: 4)
  -p/--arp-pattern ARP_PATTERN      - pattern for arpeggiation (e.g., "+3.+1...-1.+2+3" or "increment", "odd", "even")

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

``-i/--instrument`` sets the instrument from the SF2 file... here's the one I included -

```
 0 Acoustic Grand Piano
 1 Bright Acoustic Piano
 2 Electric Grand Piano
 3 Honky-tonk Piano
 4 Electric Piano 1
 5 Electric Piano 2
 6 Harpsichord
 7 Clavi
 8 Celesta
 9 Glockenspiel
10 Music Box
11 Vibraphone
12 Marimba
13 Xylophone
14 Tubular Bells
15 Dulcimer
16 Drawbar Organ
17 Percussive Organ
18 Rock Organ
19 Church Organ
20 Reed Organ
21 Accordion
22 Harmonica
23 Tango Accordion
24 Acoustic Guitar (nylon)
25 Acoustic Guitar (steel)
26 Electric Guitar (jazz)
27 Electric Guitar (clean)
28 Electric Guitar (muted)
29 Overdriven Guitar
30 Distortion Guitar
31 Guitar harmonics
32 Acoustic Bass
33 Electric Bass (finger)
34 Electric Bass (pick)
35 Fretless Bass
36 Slap Bass 1
37 Slap Bass 2
38 Synth Bass 1
39 Synth Bass 2
40 Violin
41 Viola
42 Cello
43 Contrabass
44 Tremolo Strings
45 Pizzicato Strings
46 Orchestral Harp
47 Timpani
48 String Ensemble 1
49 String Ensemble 2
50 SynthStrings 1
51 SynthStrings 2
52 Choir Aahs
53 Voice Oohs
54 Synth Voice
55 Orchestra Hit
56 Trumpet
57 Trombone
58 Tuba
59 Muted Trumpet
60 French Horn
61 Brass Section
62 SynthBrass 1
63 SynthBrass 2
64 Soprano Sax
65 Alto Sax
66 Tenor Sax
67 Baritone Sax
68 Oboe
69 English Horn
70 Bassoon
71 Clarinet
72 Piccolo
73 Flute
74 Recorder
75 Pan Flute
76 Blown Bottle
77 Shakuhachi
78 Whistle
79 Ocarina
80 Lead 1 (square)
81 Lead 2 (sawtooth)
82 Lead 3 (calliope)
83 Lead 4 (chiff)
84 Lead 5 (charang)
85 Lead 6 (voice)
86 Lead 7 (fifths)
87 Lead 8 (bass + lead)
88 Pad 1 (new age)
89 Pad 2 (warm)
90 Pad 3 (polysynth)
91 Pad 4 (choir)
92 Pad 5 (bowed)
93 Pad 6 (metallic)
94 Pad 7 (halo)
95 Pad 8 (sweep)
96 FX 1 (rain)
97 FX 2 (soundtrack)
98 FX 3 (crystal)
99 FX 4 (atmosphere)
100 FX 5 (brightness)
101 FX 6 (goblins)
102 FX 7 (echoes)
103 FX 8 (sci-fi)
104 Sitar
105 Banjo
106 Shamisen
107 Koto
108 Kalimba
109 Bag pipe
110 Fiddle
111 Shanai
112 Tinkle Bell
113 Agogo
114 Steel Drums
115 Woodblock
116 Taiko Drum
117 Melodic Tom
118 Synth Drum
119 Reverse Cymbal
120 Guitar Fret Noise
121 Breath Noise
122 Seashore
123 Bird Tweet
124 Telephone Ring
125 Helicopter
126 Applause
127 Gunshot
```
