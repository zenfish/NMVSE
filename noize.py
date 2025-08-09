#!/usr/bin/env python3

#
# connect n play with the NMVSE - the Noise Machine Strait Vibe Edition
#

import argparse
import asyncio
import coloredlogs
import fractions
import inspect
import logging
import mido
import os
import random
import signal
import sys
import threading
import time

from enum import Enum
from os   import environ

from music21 import *

# jump through various hoops
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
environ["COLOREDLOGS_LOG_FORMAT"]     = '[%(asctime)s] %(message)s'
environ["COLOREDLOGS_DATE_FORMAT"]    = '%H:%M:%S'
# 172 -> orange, 225 -> white, 190 -> yellow, etc.
environ["COLOREDLOGS_LEVEL_STYLES"]   = 'info=144;warn=172;debug=32'
environ["FLUIDSYNTH_GAIN"]            = "6.0"

import pygame.midi

# why not, import the world
import mingus.core.notes  as notes
import mingus.core.chords as chords

from   mingus.core.notes  import reduce_accidentals
from   mingus.core.chords import from_shorthand
from   mingus.midi        import fluidsynth

#
# monkey madness time
#
import mingus.midi.pyfluidsynth as pyfluid
from   mingus.midi.pyfluidsynth import fluid_settings_setnum, fluid_settings_setint, fluid_settings_setstr


### the NMSVE lil midi box

# this is mine... presuming that the hex is something like the bluetooth address... but how many
# other devices will start with NMSVE? :)
#NMSVE           = "NMSVE A4 47 16 Bluetooth"
NMSVE           = "NMSVE "


# it's a bit wobbly... but since this is essentially for a stepper function, don't do it for EVERY step
KNOB_TOLERANCE  = 10

# SF2 file?
# SF2 = "/opt/homebrew/Cellar/fluid-synth/2.4.6/share/soundfonts/default.sf2"
SF2 = "./GeneralUser-GS.sf2"

#
# various keys in the scales
#
KEY_OFFSET      = 0  # Default is C == 0

# fire up the secret harmonizerooni?
HARMONIZER      = False

# time between arppegiated notez
ARP_SNOOZE      = 0.2
ARP             = False
ARP_BPM         = 120
ARP_RATE        = fractions.Fraction(1, 4)  # Default is 1/4 notes per beat
ARP_DIRECTION   = "up"
ARP_OVERLAY     = False  # Renamed from ARP_LATCH
ARP_LATCH       = False  # New option
ARP_PATTERN_N   = 4
ARP_PATTERN     = "+1.+2.+3.+4."

# default velocity of none set
MIDI_VELOCITY   = 127

NOTES_IN_OCTAVE = 12

# until setup
midi_player     = False

# Arpeggiator state
active_arps     = {}
arp_lock        = threading.Lock()
arp_loop        = None

# Only play notes in the scale
ONLY_SCALE_PERMITTED = False

# Predefined patterns
PREDEFINED_PATTERNS = {
    "increment": "+1.+2.+3.+4.",
    "odd":       "+1.+3.+5.+7.",
    "even":      "+2.+4.+6.+8.",
    "up-down":   "+0.+1.+2.+3.+2.+1.+0.",
    "down-up":   "+0.-1.-2.-3.-2.-1.+0."
}

# Current scale (if any)
current_scale = None
current_scale_obj = None
scale_notes_midi = None

class ArpDirection(Enum):
    UP      = "up"
    DOWN    = "down"
    RANDOM  = "random"

def get_all_music21_scales():
    """Dynamically discover all concrete scale classes in music21"""
    scale_classes = {}

    # Classes to exclude - these are abstract bases or utilities, not playable scales
    excluded_classes = {
        'AbstractScale',
        'ConcreteScale',
        'DiatonicScale',
        'OctaveRepeatingScale',
        'SieveScale',
        'CyclicalScale',  # Added this
        'WeightedHexatonicBlues',  # This might be a utility class
    }

    # Patterns to exclude - anything with these patterns are likely abstract
    excluded_patterns = [
        'Abstract',
        'Concrete',
        'Sieve',
        'OctaveRepeating',
        'Cyclical',  # Added this pattern
    ]

    # Get all classes from the scale module
    for name, obj in inspect.getmembers(scale):
        if (inspect.isclass(obj) and
            issubclass(obj, scale.Scale) and
            obj != scale.Scale and
            not name.startswith('_')):

            # Skip excluded classes
            if name in excluded_classes:
                continue

            # Skip classes matching excluded patterns
            if any(pattern in name for pattern in excluded_patterns):
                continue

            # Try to instantiate with C to see if it's a concrete, usable scale
            try:
                test_scale = obj(pitch.Pitch('C'))
                # Try to get pitches - if this fails, it's probably abstract
                test_pitches = test_scale.pitches
                # If we get here, it's probably a real scale

                # Convert class name to user-friendly name
                friendly_name = name.replace('Scale', '').lower()

                # Add spaces before capital letters for compound names
                import re
                friendly_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name.replace('Scale', '')).lower()

                scale_classes[friendly_name] = obj

            except Exception as e:
                # If we can't instantiate it or get pitches, skip it
                # This catches abstract classes that can't be used directly
                continue

    # Only add aliases for scales that actually exist and work
    aliases = {}

    # Check what actually exists and add safe aliases
    if 'minor' in scale_classes:
        aliases['natural minor'] = scale_classes['minor']
        aliases['aeolian'] = scale_classes['minor']

    if 'major' in scale_classes:
        aliases['ionian'] = scale_classes['major']

    # Check for pentatonic variations
    if 'pentatonic' in scale_classes:
        aliases['major pentatonic'] = scale_classes['pentatonic']

    scale_classes.update(aliases)
    return scale_classes

def list_all_scales():
    """List all available scales with examples"""
    available_scales = get_all_music21_scales()

    print("All available scales in music21 - example notes presume the key of C")
    print("=" * 60)

    successful_scales = []
    failed_scales = []

    for scale_name in sorted(available_scales.keys()):
        try:
            # Try to create an example in C
            example_scale = available_scales[scale_name](pitch.Pitch('C'))
            notes = []

            # Get the pitches and format them nicely
            for p in example_scale.pitches:
                note_name = str(p.name)
                # Replace unicode flats/sharps with ASCII if needed
                note_name = note_name.replace('♭', 'b').replace('♯', '#').replace('-','b')
                notes.append(note_name)

            successful_scales.append((scale_name, notes))

        except Exception as e:
            failed_scales.append((scale_name, str(e)))

    # Print successful scales
    for scale_name, notes in successful_scales:
        notes_str = ' '.join(notes)
        print(f"{scale_name:25} | {notes_str}")

    # Print failed scales if any (for debugging)
    if failed_scales:
        print("\nScales that couldn't be created:")
        print("-" * 40)
        for scale_name, error in failed_scales:
            print(f"{scale_name:25} | Error: {error}")
    
    return successful_scales

def parse_fraction(fraction_str):
    logging.debug(f"In parse_fraction({fraction_str})")

    try:
        return fractions.Fraction(fraction_str)

    except ValueError:
        # Try to parse X/Y format
        try:
            if '/' in fraction_str:
                num, denom = fraction_str.split('/')
                return fractions.Fraction(int(num), int(denom))
            else:
                return fractions.Fraction(int(fraction_str), 1)
        except (ValueError, ZeroDivisionError):
            logging.error(f"Invalid fraction format: {fraction_str}. Using default 1/4.")
            return fractions.Fraction(1, 2)

def setup_logging(log_level):

    # Map log level string to numeric value
    level_map = {
        "40":          logging.DEBUG,
        "debug":       logging.DEBUG,
        "30":          logging.INFO,
        "verbose":     logging.INFO,
        "20":          logging.WARNING,
        "info":        logging.WARNING,
        "10":          logging.ERROR,
        "errors-only": logging.ERROR
    }

    # gray for timestamp
    field_styles = { 'asctime': {'color': 'white'} }

    # log_level    = level_map.get(log_level.lower(), logging.INFO)

    coloredlogs.install(level=level_map[log_level], field_styles=field_styles)

    logging.warning(f"setting up logging to: {level_map[log_level]}")

    return log_level

def setup_instrument(instrument_int, instrument_str):
    global current_instrument
    
    # num can't be any greater than the # of instruments
    if 0 <= instrument_int < len(INSTRUMENTS):
        logging.warning(f"Using instrument: {instrument_str} (#{instrument_int}) from {SF2}")

        # channel, instrument, bank
        fluidsynth.set_instrument(1, instrument_int, 0)
        current_instrument = instrument_int
        return True
    
    # If we get here, instrument wasn't found
    logging.error(f"Instrument '{instrument_arg}' not found. Available instruments:")
    for i, name in enumerate(INSTRUMENTS):
        logging.error(f"{i}: {name}")
    return False

# calculate semitone offset from C
def calculate_key_offset(key_str):
    """Calculate semitone offset from C for the given key"""
    if not key_str:
        return 0

    # Handle lowercase input and normalize
    key_str = key_str[0].upper() + key_str[1:]

    # Create a pitch object for the key and for C
    try:
        key_pitch = pitch.Pitch(key_str)
        c_pitch = pitch.Pitch('C')

        # Calculate semitone difference
        offset = key_pitch.midi - c_pitch.midi
        logging.info(f"Transposing from C to {key_str} (offset: {offset} semitones)")
        return offset
    except Exception as e:
        logging.error(f"Invalid key: {key_str}. Using C instead. Error: {e}")
        return 0

# Add this function to transpose individual notes
def transpose_note(note_str, semitones):
    """Transpose a note string by the given number of semitones"""
    # Handle empty notes
    if not note_str:
        return note_str
    
    # Parse the note
    try:
        # Create a pitch object
        p = pitch.Pitch(note_str)
        
        # Transpose by the specified number of semitones
        p.transpose(semitones, inPlace=True)
        
        # Return the new note name
        return p.name
    except Exception as e:
        logging.error(f"Error transposing note {note_str}: {e}")
        return note_str

def create_scale(key_name, scale_type):
    """Create a scale object based on key and scale type"""
    try:
        # Normalize the key name
        key_pitch = pitch.Pitch(key_name.title())
    except:
        raise ValueError(f"Invalid key: '{key_name}'. Please use a valid note name (e.g., C, D#, Bb, F#)")

    scale_type_lower = scale_type.lower()

    # Get all available scales
    available_scales = get_all_music21_scales()

    # Check if it's a custom scale format (note-note-note)
    if '-' in scale_type_lower:
        # Parse custom scale
        scale_notes = scale_type_lower.upper().split('-')
        valid_notes = set("ABCDEFG")
        
        # Validate notes
        for note in scale_notes:
            if not note or note[0] not in valid_notes:
                raise ValueError(f"Invalid note '{note}' in scale. Must start with A-G.")
        
        # Create a custom scale
        custom_scale = scale.ConcreteScale(tonic=key_pitch, pitches=[pitch.Pitch(n) for n in scale_notes])
        return custom_scale
    
    # Try exact match first
    if scale_type_lower in available_scales:
        scale_class = available_scales[scale_type_lower]
    else:
        # Try partial matching
        matches = [name for name in available_scales.keys() if scale_type_lower in name]
        if len(matches) == 1:
            scale_class = available_scales[matches[0]]
            print(f"Note: Using '{matches[0]}' for '{scale_type}'")
        elif len(matches) > 1:
            print(f"Ambiguous scale type: '{scale_type}'. Could be:")
            for match in sorted(matches):
                print(f"  - {match}")
            sys.exit(1)
        else:
            print(f"Unknown scale type: '{scale_type}'")
            print("Available scales:")
            for s in sorted(available_scales.keys()):
                print(f"  - {s}")
            sys.exit(1)

    # Create the scale
    try:
        created_scale = scale_class(key_pitch)
        return created_scale
    except Exception as e:
        raise ValueError(f"Error creating {scale_type} scale in key {key_name}: {e}")

def setup_scale(scale_arg, key_str='C'):
    global current_scale, current_scale_obj, scale_notes_midi
    
    logging.debug(f"In setup_scale({scale_arg}, {key_str})")

    if scale_arg == "help" or scale_arg == "list":
        logging.info("Available scales:\n")
        list_all_scales()
        logging.info("")
        sys.exit(0)
    
    if not scale_arg:
        logging.warning(f"No scale specified, returning None")
        return None
    
    try:
        # For custom scales with the note-note-note format
        if '-' in scale_arg:
            # Parse the custom scale directly
            scale_notes_str = scale_arg.upper().split('-')
            
            # Convert to pitch classes (0-11)
            midi_notes = []
            note_names = []
            
            for note_str in scale_notes_str:
                try:
                    # Create a pitch object
                    p = pitch.Pitch(note_str)
                    
                    # Get the pitch class (0-11)
                    pitch_class = p.midi % 12
                    
                    # Only add if not already in the scale (avoid duplicates)
                    if pitch_class not in midi_notes:
                        midi_notes.append(pitch_class)
                        note_names.append(p.name)
                except Exception as e:
                    logging.error(f"Invalid note '{note_str}' in scale: {e}")
            
            # Create the scale object for other functions that might need it
            try:
                scale_obj = scale.ConcreteScale(tonic=pitch.Pitch(key_str), pitches=[pitch.Pitch(n) for n in note_names])
            except:
                scale_obj = None
                
            logging.info(f"Using custom scale: {key_str} {scale_arg} ({' '.join(note_names)})")
            logging.debug(f"Scale MIDI notes: {midi_notes}")
            
            current_scale = note_names
            current_scale_obj = scale_obj
            scale_notes_midi = midi_notes
            
            return note_names
        
        # For music21 scales
        else:
            # Create the scale using music21
            scale_obj = create_scale(key_str, scale_arg)
            
            # Get the notes in the scale
            scale_notes = scale_obj.pitches
            
            # Format the notes for display
            note_names = []
            midi_notes = []
            
            # Process each note in the scale
            for note in scale_notes:
                note_name = str(note.name).replace('♭', 'b').replace('♯', '#')
                pitch_class = note.midi % 12
                
                # Only add if not already in the scale (avoid duplicates)
                if pitch_class not in midi_notes:
                    midi_notes.append(pitch_class)
                    note_names.append(note_name)
            
            logging.info(f"Using scale: {key_str} {scale_arg} ({' '.join(note_names)})")
            logging.debug(f"Scale MIDI notes: {midi_notes}")
            
            current_scale = note_names
            current_scale_obj = scale_obj
            scale_notes_midi = midi_notes
            
            return note_names
        
    except Exception as e:
        logging.error(f"Error setting up scale: {e}")
        return None


def is_note_in_scale(midi_note):
    """Check if a MIDI note is in the current scale"""
    if not scale_notes_midi:
        return True  # If no scale is set, all notes are allowed
    
    # Check if the note (modulo 12 for octave independence) is in our scale
    return (midi_note % 12) in scale_notes_midi

def map_to_scale(midi_note):
    """Map a MIDI note to the nearest note in the scale"""
    if not scale_notes_midi or not ONLY_SCALE_PERMITTED:
        return midi_note  # If no scale restriction, return the original note
    
    # If the note is already in the scale, return it
    if is_note_in_scale(midi_note):
        return midi_note
    
    # Find the octave and note within octave
    octave = midi_note // 12
    note_in_octave = midi_note % 12
    
    # Find the closest note in the scale
    closest_note = None
    min_distance = float('inf')
    
    for scale_note in scale_notes_midi:
        distance = abs(note_in_octave - scale_note)
        # Consider wrapping around the octave
        wrapped_distance = min(distance, 12 - distance)
        
        if wrapped_distance < min_distance:
            min_distance = wrapped_distance
            closest_note = scale_note
    
    # Construct the mapped MIDI note
    mapped_note = (octave * 12) + closest_note
    
    logging.debug(f"Mapped MIDI note {midi_note} to {mapped_note} (nearest in scale)")
    return mapped_note

def get_scale_position(midi_note):
    """Get the position of a note in the scale (for scale-restricted mode)"""
    if not scale_notes_midi or not ONLY_SCALE_PERMITTED:
        return midi_note  # Default behavior if no scale restriction
    
    # Get the note within the octave
    note_in_octave = midi_note % 12
    
    # If the note is in the scale, find its position
    if note_in_octave in scale_notes_midi:
        position = scale_notes_midi.index(note_in_octave)
        octave = midi_note // 12
        
        # Calculate the actual note in the scale across octaves
        scale_note = position + (octave * len(scale_notes_midi))
        return scale_note
    else:
        # If not in scale, map to the nearest note
        return map_to_scale(midi_note)

def get_midi_from_scale_position(position):
    """Convert a scale position to a MIDI note number"""
    if not scale_notes_midi or not ONLY_SCALE_PERMITTED:
        return position  # Default behavior if no scale restriction
    
    # Calculate octave and position within scale
    octave = position // len(scale_notes_midi)
    pos_in_scale = position % len(scale_notes_midi)
    
    # Get the note from the scale
    note_in_octave = scale_notes_midi[pos_in_scale]
    
    # Calculate the MIDI note number
    midi_note = (octave * 12) + note_in_octave
    
    return midi_note

def map_midi_key_to_scale(midi_key):
    """
    Map a MIDI key number to a note in the scale sequentially.
    Each key plays the next note in the scale.
    """
    if not scale_notes_midi or not ONLY_SCALE_PERMITTED:
        return midi_key  # If no scale restriction, return the original note
    
    # Get the scale length
    scale_length = len(scale_notes_midi)
    logging.debug(f"Scale length: {scale_length}, Scale notes: {scale_notes_midi}")
    
    # Calculate which note in the scale (0 to scale_length-1)
    scale_index = midi_key % scale_length
    
    # Get the pitch class for this scale index
    pitch_class = scale_notes_midi[scale_index]
    
    # Calculate the octave
    base_octave = 3  # Start at octave 3 (C3 = 36)
    octave_offset = (midi_key - 36) // scale_length
    octave = base_octave + octave_offset
    
    # Calculate the final MIDI note
    midi_note = (octave * 12) + pitch_class
    
    # Ensure we're in the valid MIDI range
    midi_note = max(0, min(127, midi_note))
    
    logging.debug(f"Mapped MIDI key {midi_key} to scale note {midi_note} (scale index {scale_index}, octave {octave})")
    return midi_note

def start_sound(chan, note):
    global midi_player

    logging.warning("starting note.... ")
    
    # If scale restriction is enabled, map the key to the scale sequentially
    if ONLY_SCALE_PERMITTED:
        original_note = note
        note = map_midi_key_to_scale(note)
        if original_note != note:
            logging.debug(f"Mapped key {original_note} to scale note {note}")
    
    note_str, octave = number_to_note(note)

    _note, _octave = number_to_note(note)

    # arpity, anyone?
    if ARP:
        # Start arpeggiator for this note
        logging.debug("starting the arp engine up!")
        start_arp(chan, note)

    # else chords, chords, and more chords
    elif CHORDS:
        # For chords, we need to transpose the root note before getting the chord
        if KEY_OFFSET != 0:
            # Get the transposed root note
            logging.debug(f"before transpose -> {note_str}")
            transposed_note_str = transpose_note(note_str, KEY_OFFSET)
            logging.debug(f"Transposed chord root from {note_str} to {transposed_note_str}")
            note_str            = transposed_note_str
            notez               = chords.from_shorthand(transposed_note_str)

            # -> Mapped key 48 to scale note 66
            # -> Transposed chord root from F to F

            print(f"KO: {KEY_OFFSET}")
            # _n_ = note.Note(note_str)
            # Access the .pitch.midi attribute to get the MIDI note number
            # _m_n_ = n.pitch.midi

            # print(

            # midi_note_number = 60  # Middle C
            # Create a Pitch object from the MIDI note number
            # p = pitch.Pitch()
            # p.midi = midi_note_number
            # Get the note name with octave
            # note_name = p.nameWithOctave




        else:
            notez = chords.from_shorthand(note_str)

#       print(f"NS: {note_str}")
#       note_str = note_str.replace('♭', 'b').replace('♯', '#').replace('-','b')
#       print(f"NS: {note_str}")

        logging.warning(f"{note_str} {notez}")

        last_note = 0

        logging.debug(f"\t+++> {note_str} [ch-{chan} / {notez}-{octave}]")

        for nz in notez:
            z = note_to_number(nz, _octave)
    
            if last_note > z:
                z = z + NOTES_IN_OCTAVE
            
            # If scale restriction is enabled, map chord notes to the scale
            if ONLY_SCALE_PERMITTED:
                original_z = z
                z = map_to_scale(z)
                if original_z != z:
                    logging.debug(f"Mapped chord note {original_z} to {z} (in scale)")
    
            fluidsynth.play_Note(z)
    
            last_note = note

    # the purity of a single note....
    else:
        # Apply key transposition for direct note playing
        if KEY_OFFSET != 0:
            transposed_note = note + KEY_OFFSET

            orig_note = note_str

            note_str, octave = number_to_note(transposed_note)

            logging.debug(f"\t+++> [ch-{chan} / {note_str}-{octave}] ... (Transposed {orig_note})")

            fluidsynth.play_Note(transposed_note)
        else:
            logging.debug(f"\t+++> [ch-{chan} / {note_str}-{octave}]")
            fluidsynth.play_Note(note)

# heads or tails... for random arp, up or down
def flip():
    # logging.debug("...flip dat coin....")
    return random.choice([-1,1])

def parse_arp_pattern(pattern_arg):
    # Check if it's a predefined pattern with direction prefix
    direction = None
    pattern = pattern_arg
    
    if pattern.startswith('+'):
        direction = "up"
    elif pattern.startswith('-'):
        direction = "down"
    
    # Check for predefined patterns
    if pattern.lower() in PREDEFINED_PATTERNS:
        pattern = PREDEFINED_PATTERNS[pattern.lower()]
    
    return pattern, direction

def get_note_from_scale(base_note, offset):
    if ONLY_SCALE_PERMITTED and scale_notes_midi:
        # In scale-restricted mode, we need to work with scale positions
        scale_length = len(scale_notes_midi)
        
        # Find the position of this note in our sequential mapping
        base_position = base_note % scale_length
        
        # Apply the offset within the scale
        new_position = (base_position + offset) % scale_length
        octave_change = (base_position + offset) // scale_length
        
        # Calculate the new octave
        base_octave = base_note // scale_length
        new_octave = base_octave + octave_change
        
        # Get the note from the scale
        note_in_octave = scale_notes_midi[new_position]
        
        # Calculate the MIDI note number
        midi_note = (new_octave * 12) + note_in_octave
        
        return midi_note
    elif current_scale:
        # Original scale-based logic for non-restricted mode
        # Extract the base note letter and octave
        base_note_str, base_octave = number_to_note(base_note)
        base_note_letter = base_note_str[0]  # Just the letter part, ignoring sharps/flats
        
        # Find the position of the base note in the scale
        try:
            scale_pos = next(i for i, note in enumerate(current_scale) if note.startswith(base_note_letter))
        except StopIteration:
            # Base note not in scale, fall back to semitones
            logging.debug(f"Note {base_note_str} not found in scale, using semitones")
            return base_note + offset
        
        # Calculate the new position in the scale
        new_pos = (scale_pos + offset) % len(current_scale)
        octave_shift = (scale_pos + offset) // len(current_scale)
        
        # Get the new note and convert to MIDI number
        new_note = current_scale[new_pos]
        try:
            midi_note = note_to_number(new_note, base_octave + octave_shift)

            # Apply key transposition
            midi_note += KEY_OFFSET

            return midi_note

        except:
            # If there's an error, fall back to semitones
            logging.debug(f"Error calculating scale note, using semitones")
            return base_note + offset
    else:
        # No scale defined, use semitones
        return base_note + offset


def get_arp_sequence_notes(base_note, pattern):
    """Get the actual notes that will be played in the arpeggio sequence"""
    sequence = []
    for element in pattern:
        if element == '.':
            sequence.append('rest')
        elif isinstance(element, int):
            if element == 0:
                note_num = base_note
            else:
                note_num = get_note_from_scale(base_note, element)
            
            note_str, octave = number_to_note(note_num)
            sequence.append(f"{note_str}{octave}")
    
    return sequence

async def arpeggiator_loop():
    global active_arps
    
    while True:
        # Calculate sleep time based on BPM and rate
        # Rate is notes per beat, so sleep time is (60/BPM)/rate
        sleep_time = (60.0 / ARP_BPM) * float(ARP_RATE)
        
        with arp_lock:
            # Process each active arpeggio
            for note_id, arp_data in list(active_arps.items()):
                if not arp_data['active'] and not ARP_OVERLAY:
                    # Remove inactive arps if not overlayed
                    if arp_data['current_note'] is not None:
                        fluidsynth.stop_Note(arp_data['current_note'])
                        arp_data['current_note'] = None
                    del active_arps[note_id]
                    continue
                
                # Get the current step and pattern
                step      = arp_data['step']
                pattern   = arp_data['pattern']
                base_note = arp_data['base_note']
                
                # Get the current pattern element
                if step < len(pattern):
                    element = pattern[step]
                    
                    # Process the element
                    if element == '.':
                        # Rest - stop any currently playing note
                        if arp_data['current_note'] is not None:
                            fluidsynth.stop_Note(arp_data['current_note'])
                            arp_data['current_note'] = None
                    else:  # Handle all numeric elements, including 0
                        # Stop previous note if any
                        if arp_data['current_note'] is not None:
                            fluidsynth.stop_Note(arp_data['current_note'])
                        
                        # Calculate the new note
                        if ARP_DIRECTION == "random":
                            rez = flip()
                            if rez < 0:
                                logging.info(f"scrambling pattern...")
                        else:
                            rez = 1

                        # If element is 0, use the base note directly
                        if element == 0:
                            new_note = base_note
                        else:
                            new_note = get_note_from_scale(base_note, rez * element)
                        
                        # If scale restriction is enabled, map to the scale
                        if ONLY_SCALE_PERMITTED:
                            original_note = new_note
                            new_note = map_midi_key_to_scale(new_note)
                            if original_note != new_note:
                                logging.debug(f"Mapped arp note {original_note} to {new_note} (in scale)")

                        new_note_str = number_to_note(new_note)

                        logging.warning("\tnote: %s / %s-%s" % (new_note, new_note_str[0], new_note_str[1]))

                        # Play the new note
                        fluidsynth.play_Note(new_note)
                        arp_data['current_note'] = new_note
                
                # Increment step
                arp_data['step'] = (step + 1) % len(pattern)
        
        # Sleep until next beat
        await asyncio.sleep(sleep_time)

def start_arpeggiator():
    global arp_loop
    
    if arp_loop is None:
        # Start the arpeggiator loop in a separate thread
        def run_arp_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(arpeggiator_loop())
        
        arp_thread = threading.Thread(target=run_arp_loop, daemon=True)
        arp_thread.start()
        arp_loop = arp_thread
        logging.info("Arpeggiator started")

def process_arp_pattern(pattern_str, direction=None):
    # If direction is specified, it overrides the global setting
    if direction is None:
        direction = ARP_DIRECTION
    
    logging.debug(pattern_str)

    # Parse the pattern string
    elements = []
    i = 0
    while i < len(pattern_str):
        if pattern_str[i] == '.':
            # Rest
            elements.append('.')
            i += 1
        elif pattern_str[i] in '+-':
            # Note offset
            sign = 1 if pattern_str[i] == '+' else -1
            i += 1
            num_str = ''
            while i < len(pattern_str) and pattern_str[i].isdigit():
                num_str += pattern_str[i]
                i += 1
            if num_str:
                elements.append(sign * int(num_str))
        else:
            # Skip invalid characters
            i += 1
    
    logging.debug(elements)

    # Apply direction
    if direction == "down":
        # Invert all non-rest elements
        elements = [(-e if isinstance(e, int) else e) for e in elements]
    
    return elements

def start_arp(channel, note):
    global active_arps
    
    if not ARP:
        logging.warning("hey, ARP isn't enabled, bailing from start_arp()")
        return
    
    # Parse the pattern
    logging.debug("orig pattern...")
    logging.debug(ARP_PATTERN)
    pattern_str, pattern_direction = parse_arp_pattern(ARP_PATTERN)
    logging.debug("morphed to...")
    logging.debug(pattern_str)
    pattern                        = process_arp_pattern(pattern_str, pattern_direction)
    logging.debug("final pattern...")
    logging.debug(pattern)
    
    # If latch is enabled, stop all other arps
    if ARP_LATCH:
        with arp_lock:
            for note_id, arp_data in list(active_arps.items()):
                if arp_data['current_note'] is not None:
                    fluidsynth.stop_Note(arp_data['current_note'])
                    arp_data['current_note'] = None
            active_arps.clear()
    
    # Log the sequence of notes that will be played
    sequence = get_arp_sequence_notes(note, pattern)

    logging.debug(f"ARP SEQUENCE: {sequence}")
    logging.info(f"Arp sequence for note {number_to_note(note)[0]}{number_to_note(note)[1]}: {' '.join(sequence)}")
    logging.info(f"Playing at rate: {ARP_RATE} notes per beat ({ARP_BPM} BPM)")
    
    # Create a new arpeggio entry
    with arp_lock:
        note_id = f"{channel}:{note}"
        active_arps[note_id] = {
            'base_note': note,
            'pattern': pattern,
            'step': 0,
            'active': True,
            'current_note': None
        }
    
    # Start the arp

def stop_arp(channel, note):
    global active_arps
    
    if not ARP:
        logging.warning("hey, ARP isn't enabled, bailing from stop_arp()")
        return
    
    with arp_lock:
        note_id = f"{channel}:{note}"
        if note_id in active_arps:
            # Mark as inactive (will be removed in the loop if not overlayed)
            active_arps[note_id]['active'] = False
            
            # If not overlayed, stop the current note
            if not ARP_OVERLAY and active_arps[note_id]['current_note'] is not None:
                fluidsynth.stop_Note(active_arps[note_id]['current_note'])
                active_arps[note_id]['current_note'] = None
    
    logging.debug(f"Stopped arpeggio for note {note}")

def stop_sound(chan, note):
    global midi_player

    logging.warning("\tstop!")
    
    # If scale restriction is enabled, map the key to the scale sequentially
    if ONLY_SCALE_PERMITTED:
        original_note = note
        note = map_midi_key_to_scale(note)
        if original_note != note:
            logging.debug(f"Mapped key {original_note} to scale note {note} for stop")
    
    note_str, octave = number_to_note(note)

    logging.debug("\t<--- [channel: %s] %s/%s [midi-num: %s]" % (chan, note_str, octave, note))

    _note, _octave = number_to_note(note)

    # stop arpy mcArpems
    if ARP:
        # slam on the bräx
        if not ARP_LATCH:
            stop_arp(chan, note)

    # bye bye love
    elif CHORDS:
        # For chords, we need to transpose the root note before getting the chord
        if KEY_OFFSET != 0:
            # Get the transposed root note
            transposed_note_str = transpose_note(note_str, KEY_OFFSET)
            notez = chords.from_shorthand(transposed_note_str)
        else:
            notez = chords.from_shorthand(note_str)
    
        logging.debug(notez)
    
        last_note = 0
        for nz in notez:
            z = note_to_number(nz, _octave)
    
            if last_note > z:
                z = z + NOTES_IN_OCTAVE
            
            # If scale restriction is enabled, map chord notes to the scale
            if ONLY_SCALE_PERMITTED:
                original_z = z
                z = map_to_scale(z)
                if original_z != z:
                    logging.debug(f"Mapped chord note {original_z} to {z} (in scale)")
    
            fluidsynth.stop_Note(z)
    
            last_note = note
    
    # no no note
    else:
        # Apply key transposition for direct note playing
        if KEY_OFFSET != 0:
            transposed_note = note + KEY_OFFSET
            fluidsynth.stop_Note(transposed_note)
        else:
            fluidsynth.stop_Note(note)

def get_midi_out_devices():
    logging.debug("getting midi output devices...")

    for i in range(pygame.midi.get_count()):
        r = pygame.midi.get_device_info(i)
        (interf, name, input, output, opened) = r

        if output:
            logging.info( "%2i: %s [%s]" % (i, name.decode("utf-8"), interf.decode("utf-8")))

def instrument_string_search(arg):
    inst = [i for i,v in enumerate(INSTRUMENTS) if v.lower() == arg.lower()]

    if not inst:
        logging.error(f"Couldn't find instrument {arg}")
        sys.exit(33)
    else:
        logging.debug(f"instrument {arg} == {inst}")
        return inst[0]

def signal_handler(sig, frame):
    logging.error("caught interrupt signal... shutting down....")
    stop_midi()
    sys.exit(0)

def init_midi(instrument_int, instrument_str):
    global midi_player

    logging.debug(f"initializing midi, setting instrument to {instrument_str}")

    # initialize & set instrument
    pygame.midi.init()

    default = pygame.midi.get_default_output_id()

    midi_player = pygame.midi.Output(default)
    midi_player.set_instrument(instrument_int)

#
# monkeypatching mingus fluidsynth
#

# Add the setting method to the existing Synth class
def setting(self, name, value):
    """Set a FluidSynth setting."""
    name_bytes = name.encode('utf-8') if isinstance(name, str) else name
    
    if isinstance(value, int):
        return fluid_settings_setint(self.settings, name_bytes, value)
    elif isinstance(value, float):
        return fluid_settings_setnum(self.settings, name_bytes, value)
    elif isinstance(value, str):
        value_bytes = value.encode('utf-8')
        return fluid_settings_setstr(self.settings, name_bytes, value_bytes)
    else:
        # Try as float first, then int
        try:
            return fluid_settings_setnum(self.settings, name_bytes, float(value))
        except:
            return fluid_settings_setint(self.settings, name_bytes, int(value))



def init_synth(SF2):
    logging.info(f"initializing fluidsynth")

    # squelch some of those damn errors
    try:
        # dup and close the original
        copy_of_stderr = os.dup(2)
        os.close(2)

        # use fluidsynth for sounds, that troublesome child
        fluidsynth.init(SF2)

        #
        # Monkey patch the method onto the existing class
        #
        pyfluid.Synth.setting = setting

        # the soft underbelly o' the synth
        fs = pyfluid.Synth()

        # settings are from GeneralUser-GS/documentation/README.html in the SF2 package

        # secret settings... sssssecrets.... filthy secretz.....
        fs.setting('synth.polyphony', 512)
        fs.setting('synth.device-id', 16)
        fs.setting('synth.gain', 0.5)
        fs.setting('synth.reverb.damp', 0.3)
        fs.setting('synth.reverb.level', 0.7)
        fs.setting('synth.reverb.room-size', 0.5)
        fs.setting('synth.reverb.width', 0.8)
        fs.setting('synth.chorus.depth', 3.6)
        fs.setting('synth.chorus.level', 0.55)
        fs.setting('synth.chorus.nr', 4)
        fs.setting('synth.chorus.speed', 0.36)

        fs.start()


    except Exception as e:
        print(e)
        print('woops, erzz trying to initialize fluidsynth')
        sys.exit(22)

    finally:
        # restore the old, kill off the copy
        os.dup2(copy_of_stderr, 2)
        os.close(copy_of_stderr)
        pass

def stop_midi():
    global midi_player

    logging.info("shutting down midi...")

    del midi_player
    pygame.midi.quit()

def harmonize(chord):
    print("trying to harmonize....")

    major_major = scale.MajorScale(chord)
    harm = harmony.ChordSymbol(chord)

    for h in harm:
        print(h)

    print("....")
    print(major_major)
    print("harm, iterate to h")

    import pdb
    pdb.set_trace()

    hd = harmony.ChordStepModification()
    hchord = []

    for degree in range(1, 8): # Iterate through scale degrees
        chord_on_degree = major_major.getChord(degree, 'triad')
        harmonizing_chords.append(chord_on_degree)

    print("Harmonizing chords in C Major:", [str(c) for c in harmonizing_chords])

# Constants for MIDI notes
NOTES           = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
OCTAVES         = list(range(11))
NOTES_IN_OCTAVE = len(NOTES)

errors = {
    'program': 'Bad input, please refer this spec-\nhttp://www.electronics.dit.ie/staff/tscarff/Music_technology/midi/program_change.htm',
    'notes': 'Bad input, please refer this spec-\nhttp://www.electronics.dit.ie/staff/tscarff/Music_technology/midi/midi_note_numbers_for_octaves.htm'
}

def number_to_note(number: int) -> tuple:
    octave = number // NOTES_IN_OCTAVE
    assert octave in OCTAVES, errors['notes']
    assert 0 <= number <= 127, errors['notes']
    note = NOTES[number % NOTES_IN_OCTAVE]

    return note, octave

def note_to_number(note: str, octave: int) -> int:
    note = reduce_accidentals(note)

    assert note in NOTES, errors['notes']
    assert octave in OCTAVES, errors['notes']

    note = NOTES.index(note)
    note += (NOTES_IN_OCTAVE * octave)

    assert 0 <= note <= 127, errors['notes']

    return note

def parse_args():
    parser = argparse.ArgumentParser(description='NMVSE MIDI Controller')
    
    # Arpeggiator options
    parser.add_argument('-a', '--arp',             action='store_true', help='Enable arpeggiation')
    parser.add_argument('-b', '--arp-bpm',         type=float, default=120, help='Beats per minute for arpeggiation (default: 120)')
    parser.add_argument('-c', '--chords',          action='store_true', default=True, help='Play chords')
    parser.add_argument('-r', '--arp-rate',        type=str, default="1/4", help='Rate of notes per beat as a fraction (e.g., "1/4", "1/8"). Default is 1/4.')
    parser.add_argument('-d', '--arp-direction',   choices=['up', 'down', 'random'], default='up', help='Direction of arpeggiation (default: up)')
    parser.add_argument('--arp-overlay',           action='store_true', help='Continue playing arpeggio after key release, allowing multiple arps to overlap')
    parser.add_argument('--arp-latch',             action='store_true', help='Stop previous arp sounds when starting a new sequence')
    parser.add_argument('-n', '--notes',           action='store_true', default=False, help='Play notes instead of chords')
    parser.add_argument('-na', '--arp-pattern-n',  type=int, default=4, help='Number of beats in arp pattern (default: 4)')
    parser.add_argument('-p', '--arp-pattern',     type=str, default="+1.+2.+3.+4.", help='Pattern for arpeggiation (e.g., "+3.+1...-1.+2+3" or "increment", "odd", "even")')
    
    # General options
    parser.add_argument('-f', '--sound-font-file', type=str, default="", help="alternate SF2 file")
    parser.add_argument('-i', '--instrument',      type=str, default="0", help='Instrument number or name to use; defaults to 0, which is usually the piano')
    parser.add_argument('-k', '--key',             type=str, default='C', help='Key to play in (e.g., "C", "F#", "Bb"). Default is C')
    parser.add_argument('-l', '--log-level',       type=str, default="info", choices=["10", "20", "30", "40", "errors-only", "info", "verbose", "debug"], help='Logging level (10/errors-only, 20/info, 30/verbose, 40/debug)')
    parser.add_argument('-s', '--scale',           type=str, help='Scale to use (e.g., "C-D-E-F-G-A-B" or predefined scale name)')
    
    # New option for scale-restricted mode
    parser.add_argument('--only-scale-permitted',  action='store_true', help='Only allow notes that are in the specified scale')
    
    args = parser.parse_args()
    
    return args

# List of General MIDI instruments
INSTRUMENTS = [
    'Acoustic Grand Piano', 'Bright Acoustic Piano', 'Electric Grand Piano', 'Honky-tonk Piano', 'Electric Piano 1', 'Electric Piano 2', 'Harpsichord', 'Clavi', 'Celesta', 'Glockenspiel', 'Music Box', 'Vibraphone', 'Marimba', 'Xylophone', 'Tubular Bells', 'Dulcimer', 'Drawbar Organ', 'Percussive Organ', 'Rock Organ', 'Church Organ', 'Reed Organ', 'Accordion', 'Harmonica', 'Tango Accordion', 'Acoustic Guitar (nylon)', 'Acoustic Guitar (steel)', 'Electric Guitar (jazz)', 'Electric Guitar (clean)', 'Electric Guitar (muted)', 'Overdriven Guitar', 'Distortion Guitar', 'Guitar harmonics', 'Acoustic Bass', 'Electric Bass (finger)', 'Electric Bass (pick)', 'Fretless Bass', 'Slap Bass 1', 'Slap Bass 2', 'Synth Bass 1', 'Synth Bass 2', 'Violin', 'Viola', 'Cello', 'Contrabass', 'Tremolo Strings', 'Pizzicato Strings', 'Orchestral Harp', 'Timpani', 'String Ensemble 1', 'String Ensemble 2', 'SynthStrings 1', 'SynthStrings 2', 'Choir Aahs', 'Voice Oohs', 'Synth Voice', 'Orchestra Hit', 'Trumpet', 'Trombone', 'Tuba', 'Muted Trumpet', 'French Horn', 'Brass Section', 'SynthBrass 1', 'SynthBrass 2', 'Soprano Sax', 'Alto Sax', 'Tenor Sax', 'Baritone Sax', 'Oboe', 'English Horn', 'Bassoon', 'Clarinet', 'Piccolo', 'Flute', 'Recorder', 'Pan Flute', 'Blown Bottle', 'Shakuhachi', 'Whistle', 'Ocarina', 'Lead 1 (square)', 'Lead 2 (sawtooth)', 'Lead 3 (calliope)', 'Lead 4 (chiff)', 'Lead 5 (charang)', 'Lead 6 (voice)', 'Lead 7 (fifths)', 'Lead 8 (bass + lead)', 'Pad 1 (new age)', 'Pad 2 (warm)', 'Pad 3 (polysynth)', 'Pad 4 (choir)', 'Pad 5 (bowed)', 'Pad 6 (metallic)', 'Pad 7 (halo)', 'Pad 8 (sweep)', 'FX 1 (rain)', 'FX 2 (soundtrack)', 'FX 3 (crystal)', 'FX 4 (atmosphere)', 'FX 5 (brightness)', 'FX 6 (goblins)', 'FX 7 (echoes)', 'FX 8 (sci-fi)', 'Sitar', 'Banjo', 'Shamisen', 'Koto', 'Kalimba', 'Bag pipe', 'Fiddle', 'Shanai', 'Tinkle Bell', 'Agogo', 'Steel Drums', 'Woodblock', 'Taiko Drum', 'Melodic Tom', 'Synth Drum', 'Reverse Cymbal', 'Guitar Fret Noise', 'Breath Noise', 'Seashore', 'Bird Tweet', 'Telephone Ring', 'Helicopter', 'Applause', 'Gunshot' 
]


#
# and so it begins...
#

# Check if NMSVE is available... assume any starting with NMSVE is ok....
# if NMSVE not in mido.get_input_names():
found = False
for dev in mido.get_input_names():
    if dev.startswith(NMSVE):
        NMSVE = dev
        found = True
        break
if not found:
    logging.error("can't see the NMSVE machine....")
    sys.exit(2)


# Parse command line arguments
args = parse_args()

# Setup logging
setup_logging(args.log_level)

# Set arpeggiator options
ARP             = args.arp
ARP_BPM         = args.arp_bpm
ARP_RATE        = parse_fraction(args.arp_rate)
ARP_DIRECTION   = args.arp_direction
ARP_OVERLAY     = args.arp_overlay
ARP_LATCH       = args.arp_latch
ARP_PATTERN_N   = args.arp_pattern_n
ARP_PATTERN     = args.arp_pattern

# Set scale restriction option
ONLY_SCALE_PERMITTED = args.only_scale_permitted

# Set key transposition
KEY_OFFSET = calculate_key_offset(args.key)

if args.sound_font_file:
    SF2 = args.sound_font_file

# chords or single notes?
CHORDS = True
if args.notes:
    logging.info("playing notes instead of chords")
    CHORDS = False

# Setup scale
if args.scale:
    setup_scale(args.scale, args.key)
    
    if ONLY_SCALE_PERMITTED:
        logging.info("Scale restriction enabled: Only notes in the scale will be played")
        if not current_scale:
            logging.warning("Scale restriction requested but no valid scale provided. All notes will be allowed.")
            ONLY_SCALE_PERMITTED = False

# catch interrupts
signal.signal(signal.SIGINT,  signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

#
# convert instrument to string or int
#
# currently can't lookup names in arbitrary sf2 files
#
if not args.instrument.isdigit() and args.sound_font_file:
    logging.error("Can't look up instrument names in arbitrary SF2 files")
    sys.exit(44)

#
# default SF2 file
#
if not args.sound_font_file:
    # choose/defaults to an integer for an instrument, look up the name
    if args.instrument.isdigit():
        instrument_str = INSTRUMENTS[int(args.instrument)]
        instrument_int = int(args.instrument)
    # if you tried an instrument on its name, see if we can find it in the default midi set of instruments
    else:
        instrument_int = instrument_string_search(args.instrument)
        instrument_str = args.instrument

    logging.debug("Default SF2, instrument %s/%s" % (instrument_str, instrument_int))
#
# rando SF2 file
#
else:
    instrument_int = int(args.instrument)
    instrument_str = str(instrument_int)

#
# fluidsynth care n feeding
#
init_synth(SF2)

# Setup instrument
if not setup_instrument(instrument_int, instrument_str):
    init_midi(0, "Default")
else:
    # start midi engines
    init_midi(instrument_int, instrument_str)

# what's there?
get_midi_out_devices()

if ARP:
    logging.info(f"Arpeggiation enabled: BPM={ARP_BPM}, Rate={ARP_RATE}, Direction={ARP_DIRECTION}")
    logging.info(f"Overlay={ARP_OVERLAY}, Latch={ARP_LATCH}")
    logging.info(f"Pattern: {ARP_PATTERN}")
    logging.info("ready to arp!")
    
    # Start the arpeggiator
    start_arpeggiator()
else:
    logging.info("no mas arpy")

logging.warning("galloping along with our polling... time to start interacting with NMVSE!")
logging.info("Listening for input from %s" % NMSVE)

current_value = 0
last_control_change = 0
fluidsynth_gain = environ["FLUIDSYNTH_GAIN"]

#
# keep listening until ... 
#
with mido.open_input(NMSVE) as incoming:
    for msg in incoming:
        # notes, chords, whatever
        if msg.type == "note_on":

            msg.note = msg.note - 12
            # print("MidiNote: %s" % msg.note)

            note_str, octave = number_to_note(msg.note)

            if HARMONIZER:
                logging.info("harmonizer....")
                logging.info("%s-%s" % (note_str, octave))
                harmonize(note_str)
            else:
                start_sound(msg.channel, msg.note)

        elif msg.type == "note_off":
            msg.note = msg.note - 12
            stop_sound(msg.channel, msg.note)

        elif msg.type == "polytouch":
            print(msg)

        #
        # use the NMSME rotator to change volume
        #
        elif msg.type == "control_change":
            current_value = msg.value

            # because... my noise midi is a bit... noisy... only do somethin if it' moves more than... a X or more
            if not current_value:
                current_value = int(msg.value)
                last_control_change = current_value
                continue

            if abs(current_value - last_control_change) > KNOB_TOLERANCE:
                GAIN = current_value / 127 * 100
                logging.debug(f"Changing gain to: {GAIN}")
                # Set the gain
                # channel, gain, value (0-100?)
                fluidsynth.control_change(1, 7, int(GAIN))
                last_control_change = current_value

        elif msg.type == "program_change":
            print(msg)

        elif msg.type == "aftertouch":
            print(msg)

        elif msg.type == "pitchwheel":
            print(msg)

        else:
            logging.warning("not sure how to handle message type - %s" % msg.type)
            continue


# probably won't get to this, given the loop above and so on....
stop_midi()

