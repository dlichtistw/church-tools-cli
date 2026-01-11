import pytest
import unittest.mock
import io

from .song import Song, ImportedSong, try_read_song, read_song

class TestSong:

  def test_init( self ):

    title = "Amazing Grace"

    song = Song( title )

    assert song.title == title
    assert song.key is None
    assert song.author is None
    assert song.copyright is None
    assert song.ccli is None
    assert song.categories == []

class TestImportedSong:

  def test_init( self ):

    title = "Amazing Grace"
    file_name = "amazing_grace.sng"

    song = ImportedSong( title, file_name )

    assert song.title == title
    assert song.file_name == file_name

class TestTryReadSong:

  def test_valid_song( self ):

    title = "Amazing Grace"
    key = "G"
    author = "John Newton"
    copyright = "Public Domain"
    ccli = "123456"
    categories = [ "Hymn", "Classic" ]

    content = f"""
#Title={ title }
#Key={ key }
#Author={ author }
#(c)={ copyright }
#CCLI={ ccli }
#Categories={ ", ".join( categories ) }

Amazing grace, how sweet the sound,
That saved a wretch like me!"""

    path = "amazing_grace.sng"

    with unittest.mock.patch( "builtins.open", unittest.mock.mock_open( read_data=content ) ):

      song = try_read_song( path, "utf_8" )

      assert song is not None
      assert song.title == title
      assert song.key == key
      assert song.author == author
      assert song.copyright == copyright
      assert song.ccli == ccli
      assert song.categories == categories
      assert song.file_name == path
  
  def test_missing_title( self ):

    key = "C"
    author = "Joseph Scriven"
    copyright = "Public Domain"
    ccli = "123456"
    categories = [ "Hymn", "Classic" ]

    content = f"""
#Key={ key }
#Author={ author }
#(c)={ copyright }
#CCLI={ ccli }
#Categories={ ", ".join( categories ) }

What a Friend we have in Jesus,
All our sins and griefs to bear!"""

    path = "what_a_friend_we_have_in_jesus.sng"

    with unittest.mock.patch( "builtins.open", unittest.mock.mock_open( read_data=content ) ):
      song = try_read_song( path, "utf_8" )

      assert song is None

class TestReadSong:

  def test_utf8( self ):

    title = "Test Song"
    path = "test_song.sng"
    
    with unittest.mock.patch( "SongBeamer.song.try_read_song" ) as mock:
      mock.return_value = ImportedSong( title, path )

      song = read_song( path )

      assert song is not None
      assert song.title == title
      assert song.file_name == path
      mock.assert_called_once_with( path, "utf_8_sig" )

  def test_latin1( self ):

    title = "Test Song"
    path = "test_song.sng"
    
    with unittest.mock.patch( "SongBeamer.song.try_read_song" ) as mock:
      mock.side_effect = ( UnicodeDecodeError( "", b"", 0, 0, "no reason" ), ImportedSong( "Test Song", path ), )

      song = read_song( path )

      assert song is not None
      assert song.title == title
      assert song.file_name == path
