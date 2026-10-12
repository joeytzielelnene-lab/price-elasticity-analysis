"""Song data for "Boo-Boo's Halloween Night": timing, chords, melody and lyrics.

100 BPM, 4/4, 100 bars = exactly 240 seconds.
"""

BPM = 100
BEAT = 60.0 / BPM          # 0.6 s
BAR = 4 * BEAT             # 2.4 s
TOTAL_BARS = 100
DURATION = TOTAL_BARS * BAR  # 240 s

# note names -> MIDI
_N = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def n(name):
    """'C4', 'F#4', 'Bb3' -> MIDI number; None stays None (rest)."""
    if name is None:
        return None
    pc = _N[name[0]]
    rest = name[1:]
    if rest[0] == "#":
        pc += 1
        rest = rest[1:]
    elif rest[0] == "b":
        pc -= 1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + pc


def mel(*pairs):
    return [(n(p), d) for p, d in pairs]


CHORDS = {
    "C": ["C3", "E3", "G3"], "Am": ["A2", "C3", "E3"], "F": ["F2", "A2", "C3"],
    "G": ["G2", "B2", "D3"], "Dm": ["D3", "F3", "A3"], "Em": ["E3", "G3", "B3"],
}

# ---------------------------------------------------------------- melodies
VERSE_MEL = [
    mel(("C4", .5), ("C4", .5), ("E4", .5), ("E4", .5), ("G4", .5), ("G4", .5), ("E4", 1)),
    mel(("F4", .5), ("F4", .5), ("A4", .5), ("A4", .5), ("G4", 2)),
    mel(("E4", .5), ("E4", .5), ("G4", .5), ("G4", .5), ("C5", .5), ("C5", .5), ("G4", 1)),
    mel(("F4", .5), ("E4", .5), ("D4", .5), ("E4", .5), ("C4", 2)),
    mel(("C4", .5), ("C4", .5), ("E4", .5), ("E4", .5), ("G4", .5), ("G4", .5), ("E4", 1)),
    mel(("F4", .5), ("F4", .5), ("A4", .5), ("A4", .5), ("G4", 2)),
    mel(("A4", .5), ("A4", .5), ("G4", .5), ("G4", .5), ("F4", .5), ("F4", .5), ("E4", .5), ("D4", .5)),
    mel(("G4", .5), ("G4", .5), ("F4", .5), ("D4", .5), ("C4", 2)),
]
VERSE_CH = ["C", "F", "C", "G", "C", "F", "F", "G"]

CHORUS_MEL = [
    mel(("G4", 1), ("E4", 1), ("G4", 1), ("E4", 1)),
    mel(("A4", 1), ("G4", 1), ("E4", 2)),
    mel(("F4", 1), ("D4", 1), ("F4", 1), ("D4", 1)),
    mel(("G4", 1), ("F4", 1), ("D4", 2)),
    mel(("C5", 1), (None, 1), ("C5", 1), (None, 1)),
    mel(("A4", 1), ("G4", 1), ("E4", 2)),
    mel(("E4", 1), ("F4", 1), ("G4", 1), ("A4", 1)),
    mel(("D4", 1), ("C4", 3)),
]
CHORUS_CH = ["C", "Am", "Dm", "G", "F", "Am", "F", "C"]

CHANT_MEL = [
    mel(("G4", 1), ("G4", 1), ("G4", .5), ("A4", .5), ("G4", 1)),
    mel(("E5", 1), (None, 1), ("C5", 1), (None, 1)),
    mel(("A4", .5), ("A4", .5), ("G4", .5), ("G4", .5), ("F4", .5), ("F4", .5), ("E4", 1)),
    mel(("G5", 1), (None, 1), ("E5", 1), (None, 1)),
]
CHANT_CH = ["C", "C", "F", "G"]

BRIDGE_MEL = [
    mel(("C4", 1), ("D4", .5), ("E4", .5), ("G4", 1), ("C5", 1)),
    mel(("D4", 1), ("E4", .5), ("F4", .5), ("A4", 1), ("D5", 1)),
    mel(("E4", 1), ("F4", .5), ("G4", .5), ("B4", 1), ("E5", 1)),
    mel(("F4", 1), ("G4", .5), ("A4", .5), ("C5", 1), ("F5", 1)),
    mel(("G4", 1), ("A4", .5), ("B4", .5), ("C5", 1), ("C5", 1)),
    mel(("D5", 1), ("C5", 1), ("G4", 2)),
    mel(("E5", 1), ("D5", 1), ("C5", 2)),
    mel(("G4", .5), ("A4", .5), ("B4", 1), ("C5", 2)),
]
BRIDGE_CH = ["C", "Dm", "Em", "F", "G", "C", "C", "G"]

INTRO_MEL = [mel((None, 4))] * 4
INTRO_CH = ["C", "Am", "F", "G"]
OUTRO_MEL = [
    mel(("C5", 2), ("G4", 2)), mel(("A4", 2), ("E4", 2)),
    mel(("F4", 2), ("G4", 2)), mel(("C4", 4)),
]
OUTRO_CH = ["C", "Am", "F", "C"]

# ---------------------------------------------------------------- sections
# (name, kind, bars, melody, chords, transpose)
SECTIONS = [
    ("intro", "intro", 4, INTRO_MEL, INTRO_CH, 0),
    ("verse1", "verse", 8, VERSE_MEL, VERSE_CH, 0),
    ("chorus1", "chorus", 8, CHORUS_MEL, CHORUS_CH, 0),
    ("verse2", "verse", 8, VERSE_MEL, VERSE_CH, 0),
    ("chant_pip", "chant", 4, CHANT_MEL, CHANT_CH, 0),
    ("chorus2", "chorus", 8, CHORUS_MEL, CHORUS_CH, 0),
    ("verse3", "verse", 8, VERSE_MEL, VERSE_CH, 0),
    ("chant_bella", "chant", 4, CHANT_MEL, CHANT_CH, 0),
    ("chorus3", "chorus", 8, CHORUS_MEL, CHORUS_CH, 0),
    ("verse4", "verse", 8, VERSE_MEL, VERSE_CH, 0),
    ("chant_wanda", "chant", 4, CHANT_MEL, CHANT_CH, 0),
    ("bridge", "bridge", 8, BRIDGE_MEL, BRIDGE_CH, 0),
    ("final_a", "chorus", 8, CHORUS_MEL, CHORUS_CH, 0),
    ("final_b", "chorus", 8, CHORUS_MEL, CHORUS_CH, 2),
    ("outro", "outro", 4, OUTRO_MEL, OUTRO_CH, 0),
]


def section_starts():
    out, bar = {}, 0
    for name, kind, bars, *_ in SECTIONS:
        out[name] = (bar * BAR, (bar + bars) * BAR, kind)
        bar += bars
    assert bar == TOTAL_BARS
    return out


START = section_starts()

# ---------------------------------------------------------------- lyrics
# Each lyric: (section, bar_in_section, beat_offset, length_beats, text, voice)
# voice: "lead" (narrator-singer), "kids" (chorus response), "boo" (Boo-Boo),
#        "silent" (on-screen only)
CHORUS = [
    "Boo-Boo, Boo-Boo, floating slow,",
    "Which way, which way, should we go?",
    "Boo! (Boo!) Boo! (Boo!) Sing with me —",
    "Home, home, that's where we'll be!",
]
FINAL_A = [
    "Boo-Boo, Boo-Boo, home at last,",
    "Thank you, friends, that was a blast!",
    "Boo! (Boo!) Boo! (Boo!) Sing with me —",
    "Friends help friends, yes, you will see!",
]
FINAL_B = [
    "Boo-Boo, Boo-Boo, floating slow,",
    "Now you know which way to go!",
    "Boo! (Boo!) Boo! (Boo!) Everybody —",
    "Happy, happy Halloween to you and me!",
]
VERSES = {
    "verse1": [
        "On Halloween the moon was bright,",
        "Little Boo-Boo floated out tonight.",
        "He chased a leaf that twirled around,",
        "Up and down and round and round!",
        "Past the trees and past the hill,",
        "Everything was quiet and still...",
        "He looked to the left, he looked to the right —",
        "\"Oh my! I'm lost on Halloween night!\"",
    ],
    "verse2": [
        "Then down the path, what did he see?",
        "A round orange pumpkin, smiling with glee!",
        "\"Hello, I'm Pip! Please don't be sad,",
        "I'll be your friend, and that makes me glad!\"",
        "Pip took a breath and — oh, so bright! —",
        "He lit the path with a warm, warm light.",
        "Glow, glow, glowing near,",
        "\"Come along, Boo-Boo, the path is clear!\"",
    ],
    "verse3": [
        "Up in a tree, what did they see?",
        "A little bat, as small as can be!",
        "Hanging upside-down with a giggly grin,",
        "\"Hi, I'm Bella! Can I join in?\"",
        "She flapped up high, so high, so far,",
        "Past the clouds to the twinkly star.",
        "\"I see the hill where the lanterns glow —",
        "Follow me, friends, that's the way to go!\"",
    ],
    "verse4": [
        "But the hill was big, and the hill was tall,",
        "And Boo-Boo felt so very small...",
        "Then — swish, swoosh! — sparkles in the sky,",
        "A friendly witch came flying by!",
        "\"I'm Wanda! Hello! Now don't you fret,",
        "This will be the best ride yet!",
        "Hop on my broom, there's room for three,",
        "Hold on tight and fly with me!\"",
    ],
}
CHANTS = {
    "chant_pip": ("Roll, roll, roll along,", "Glow! Glow!", "Pumpkin Pip is big and strong!", "Glow! Glow!"),
    "chant_bella": ("Flap, flap, flap your wings,", "Squeak! Squeak!", "Bella Bat just loves to sing!", "Squeak! Squeak!"),
    "chant_wanda": ("Swish, swoosh, round we go,", "Wheee!", "Wanda's broom flies nice and slow!", "Wheee!"),
}


def lyrics():
    L = []
    L.append(("intro", 1, 0, 8, "It's Halloween night in Moonbeam Hollow... ooh, look! It's Boo-Boo!", "lead"))
    for sec, lines in VERSES.items():
        for i, t in enumerate(lines):
            L.append((sec, i, 0, 4, t, "lead"))
    for sec, lines in (("chorus1", CHORUS), ("chorus2", CHORUS), ("chorus3", CHORUS),
                       ("final_a", FINAL_A), ("final_b", FINAL_B)):
        for i, t in enumerate(lines):
            if i == 2:
                L.append((sec, 4, 0, 8, t, "silent"))
                for b, voice in ((0, "lead"), (1, "kids"), (2, "lead"), (3, "kids")):
                    L.append((sec, 4, b, 1, "Boo!", voice))
                tail = "Everybody!" if sec == "final_b" else "Sing with me!"
                L.append((sec, 5, 0, 4, tail, "lead"))
            else:
                L.append((sec, 2 * i, 0, 8, t, "lead"))
    for sec, (a, ra, b, rb) in CHANTS.items():
        L.append((sec, 0, 0, 4, a, "lead"))
        L.append((sec, 1, 0, 4, ra, "kids"))
        L.append((sec, 2, 0, 4, b, "lead"))
        L.append((sec, 3, 0, 4, rb, "kids"))
    nums = ["One", "Two", "Three", "Four"]
    for i, w in enumerate(nums):
        L.append(("bridge", i, 0, 3, f"{w} little star{'s' if i else ''},", "lead"))
        L.append(("bridge", i, 3, 1, f"{w}!", "kids"))
    L.append(("bridge", 4, 0, 8, "Five little stars light up the way —", "lead"))
    L.append(("bridge", 6, 0, 8, "\"There's my house! Hooray, hooray!\"", "boo"))
    L.append(("outro", 0, 0, 4, "Goodnight, friends... Happy Halloween!", "boo"))
    L.append(("outro", 2, 0, 6, "Happy Halloween from LunaKids! Bye-bye!", "lead"))
    L.append(("outro", 3, 1, 1, "boo!", "boo"))
    out = []
    for sec, bar, beat, length, text, voice in L:
        t0 = START[sec][0] + bar * BAR + beat * BEAT
        out.append(dict(section=sec, t0=t0, t1=t0 + length * BEAT, text=text, voice=voice))
    out.sort(key=lambda d: d["t0"])
    return out


def caption_lines():
    """Lines shown on screen as karaoke captions (no duplicate 'Boo!' calls)."""
    caps = []
    for d in lyrics():
        if d["voice"] == "kids" and d["text"] == "Boo!":
            continue
        if d["voice"] == "lead" and d["text"] in ("Boo!", "Sing with me!", "Everybody!"):
            continue
        caps.append(d)
    return caps
