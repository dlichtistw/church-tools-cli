"""The SongBeamer Package

The SongBeamer package supports in handling SongBeamer data. This currently means reading .sng files.

SongBeamer is a software for presenting song lyrics and other content during church services and other events.
The author of this package is in no way affiliated to that software.
See https://songbeamer.de/ for more information on them.
"""

from .song import ImportedSong
from .song import read_song
