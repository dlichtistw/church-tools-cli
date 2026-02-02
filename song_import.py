#!/usr/bin/env python3

import datetime
import types
import requests, requests.adapters
import os
import enum

import SongBeamer
import ChurchTools
from schema import sanitize

ccli_schema = { "maxLength": 50, "type": ( "string",  "null" ) }
name_schema = { "minLength": 2, "maxLength": 200, "type": "string" }
copyright_schema = { "maxLength": 400, "type": ( "string",  "null" ) }
author_schema = { "maxLength": 300, "type": ( "string",  "null" ) }
key_schema = {
  "anyOf": [
    {
      "enum": [ "A", "Ab", "Am", "B", "Bb", "Bbm", "Bm", "C", "C#m", "Cm", "D", "D#m", "Db", "Dm", "E", "Eb", "Ebm", "Em", "F", "F#", "F#m", "Fm", "G", "G#m", "Gb", "Gm" ],
      "type": "string"
    },
    { "type": "null", }
  ]
}

def sanitize_song( song: SongBeamer.song.Song ):
  song.author = sanitize( song.author, author_schema )
  song.title = sanitize( song.title, name_schema )
  song.ccli = sanitize( song.ccli, ccli_schema )
  song.copyright = sanitize( song.copyright, copyright_schema )
  song.key = sanitize( song.key, key_schema )

class Ambiguous:
  pass

class AttachmentMode( enum.Enum ):
  ADD = "add"
  SKIP = "skip"
  REPLACE = "replace"

  def __str__( self ) -> str:
    return self.value

class ChurchToolsSession( ChurchTools.Session ):

  source_id: int | None = None
  arrangement_name: str = "SongBeamer"
  song_category: int = 0

  def __init__( self, api_url: str, *, api_token: str | None, user: str | None ):
    super().__init__( api_url, api_token )

    if user:
      self.login( user )

    retries = requests.adapters.Retry( total=5, backoff_factor=1, allowed_methods=None, status_forcelist={ 429, } )
    self.mount( self.api_url, requests.adapters.HTTPAdapter( max_retries=retries ) )

    if result := self.get( self.endpoint_url( "whoami" ) ):
      data = result.json()[ "data" ]
      print( f"Authenticated as { data[ "firstName" ] } { data[ "lastName" ] } (ID: { data[ "id" ] })." )
    else:
      raise ConnectionError( f"Failed to authenticate: { result.status_code } - { result.text }." )

    if result := self.get( self.endpoint_url( "csrftoken" ) ):
      if token := result.json().get( "data" ):
        self.headers.update( { "CSRF-Token": token } )
      else:
        raise ConnectionError( "Failed to obtain CSRF token: No token in response." )
    else:
      raise ConnectionError( f"Failed to obtain CSRF token: { result.status_code } - { result.text }" )

  def match_arrangement( self, song: SongBeamer.ImportedSong, arrangements: list[ dict ] ) -> dict | None:
    for arrangement in arrangements:
      if self.source_id is None or arrangement.get( "sourceId" ) == self.source_id:
        for file in arrangement.get( "files", [] ):
          if file.get( "name" ) == os.path.basename( song.file_name ):
            return arrangement

  def match_song( self, song: SongBeamer.ImportedSong, candidates: list[ dict ] ) -> dict | Ambiguous | None:
    for s in candidates:
      if self.match_arrangement( song, s.get( "arrangements", [] ) ):
        return s

    if song.ccli:
      for s in candidates:
        if s.get( "ccli" ) == song.ccli:
          return s
      else:
        candidates = [ s for s in candidates if "ccli" not in s ]

    if song.author:
      for s in candidates:
        if s.get( "author" ) == song.author:
          return s
      else:
        candidates = [ s for s in candidates if "author" not in s ]

    if len( candidates ) == 1:
      return candidates[ 0 ]
    elif len( candidates ) > 1:
      return Ambiguous()
    else:
      return None
    
  def import_song( self, song: SongBeamer.ImportedSong ) -> dict | None:

    songs = self.collect( requests.Request( "GET", self.api_url + "/songs", params={ "name": song.title } ) )
    for s in songs:
      if "arrangements" not in s:
        s[ "arrangements" ] = self.collect( requests.Request( "GET", f"{ self.api_url }/songs/{ s[ "id" ] }/arrangements" ) )

    match self.match_song( song, songs ):
      case dict() as existing:

        update = { k: v for k, v in existing.items() if k in [ "name", "author", "ccli", "copyright" ] }
        update[ "categoryId" ] = existing[ "category" ][ "id" ]

        sanitize_song( song )
      
        needs_update = False

        if song.ccli and song.ccli != update.get( "ccli" ):
          update[ "ccli" ] = song.ccli
          needs_update = True
    
        if song.author and song.author != update.get( "author" ):
          update[ "author" ] = song.author
          needs_update = True

        if song.copyright and song.copyright != update.get( "copyright" ):
          update[ "copyright" ] = song.copyright
          needs_update = True
        
        if needs_update:
          print( f"Updating existing song: { existing[ "id" ] } - { existing[ "name" ] }" )
          if result := self.put( f"{ self.api_url }/songs/{ existing[ "id" ] }", json=update ):
            pass
          else:
            raise ConnectionError( f"Failed to update song { existing[ "id" ] }: { result.status_code } - { result.text }" )
        else:
          print( f"Keep existing song: { existing[ "id" ] } - { existing[ "name" ] }" )
          
        return existing
    
      case None:
        print( f"Creating new song: { song.title }" )

        insert: dict = { "name": song.title, "categoryId": self.song_category }

        if song.ccli:
          insert[ "ccli" ] = song.ccli
        
        if song.author:
          insert[ "author" ] = song.author

        if song.copyright:
          insert[ "copyright" ] = song.copyright
        
        if result := self.post( self.api_url + "/songs", json=insert ):
          return result.json()[ "data" ]
        else:
          raise ConnectionError( f"Faile to create song: { result.status_code } - { result.text }" )
        
      case Ambiguous():
        print( f"Could not match song '{ song.title }'." )

  def import_arrangement( self, song: SongBeamer.ImportedSong, ct_song: dict ) -> dict:
    match self.match_arrangement( song, ct_song.get( "arrangements", [] ) ):
      case dict() as existing:

        update = { k: v for k, v in existing.items() if k in [ "beat", "duration", "key", "name", "sourceId", "tempo" ] }
        update[ "description" ] = f"Updated from '{ os.path.basename( song.file_name ) }' on { datetime.date.today().isoformat() }."

        needs_update = False

        if song.key and song.key != update.get( "key" ):
          update[ "key" ] = song.key
          needs_update = True

        if self.source_id and self.source_id != update.get( "sourceId" ):
          update[ "sourceId" ] = self.source_id
          needs_update = True

        if needs_update:
          print( f"Updating existing arrangement { existing[ "id" ] } for song id { ct_song[ "id" ] }." )
          if result := self.put( f"{ self.api_url }/songs/{ ct_song[ "id" ] }/arrangements/{ existing[ "id" ] }", json=update ):
            pass
          else:
            raise ConnectionError( f"Failed to update arrangement { existing[ "id" ] } of song { ct_song[ "id" ] }: { result.status_code } - { result.text }" )
        else:
          print( f"Keeping existing arrangement { existing[ "id" ] } for song id { ct_song[ "id" ] }." )
      
        return existing
      
      case None:
        print( f"Creating new arrangement for song id { ct_song[ "id" ] }." )

        insert: dict = {
          "name": self.arrangement_name,
          "description": f"Created from '{ os.path.basename( song.file_name ) }' on { datetime.date.today().isoformat() }"
        }

        if self.source_id:
          insert[ "sourceId" ] = self.source_id

        if song.key:
          insert[ "key" ] = song.key

        if result := self.post( f"{ self.api_url }/songs/{ ct_song[ "id" ] }/arrangements", json=insert ):
          return result.json()[ "data" ]
        else:
          raise ConnectionError( f"Failed to create arrangement: { result.status_code } - { result.text }." )

  def import_attachment( self, song: SongBeamer.ImportedSong, arrangement: dict, mode: AttachmentMode = AttachmentMode.SKIP ):
    if mode != AttachmentMode.ADD:

      arrangement[ "files" ] = self.collect( requests.Request( "GET", f"{ self.api_url }/files/song_arrangement/{ arrangement[ "id" ] }" ) )
    
      for file in arrangement.get( "files", [] ):
        if file.get( "name" ) == os.path.basename( song.file_name ):
          if mode == AttachmentMode.SKIP:
            print( f"Keeping existing attachment { file[ "id" ] } for arrangement { arrangement[ "id" ] }." )
            return
          elif mode == AttachmentMode.REPLACE:
            print( f"Deleting existing attachment { file[ "id" ] } for arrangement { arrangement[ "id" ] }." )
            if result := self.delete( f"{ self.api_url }/files/{ file[ "id" ] }" ):
              pass
            else:
              raise ConnectionError( f"Failed to delete attachment { file[ "id" ] }: { result.status_code } - { result.text }" )
      
    print( f"Uploading attachment '{ os.path.basename( song.file_name ) }' for arrangement { arrangement[ "id" ] }." )
    with open( song.file_name, "rb" ) as file:
      files = { "files[]": ( os.path.basename( song.file_name ), file ) }
      if result := self.post( f"{ self.api_url }/files/song_arrangement/{ arrangement[ "id" ] }", files=files ):
        return
      else:
        raise ConnectionError( f"Failed to upload attachment for arrangement { arrangement[ "id" ] }: { result.status_code } - { result.text }" )
    
    
  def set_default_arrangement( self, song_id: int, arrangement_id: int ):
    if result := self.patch( f"{ self.api_url }/songs/{ song_id }/arrangements/{ arrangement_id }/default" ):
      return
    else:
      raise ConnectionError( f"Failed to set arrangement { arrangement_id } as default for song { song_id }: { result.status_code } - { result.text }" )
    
  def delete_imported_songs( self ):
    if self.source_id is None:
      raise ValueError( "source_id must be set to delete imported songs." )

    for song in self.collect( requests.Request( "GET", self.api_url + "/songs", params={ "sourceId": self.source_id } ) ):

      delete_song = True

      for arrangement in self.collect( requests.Request( "GET", f"{ self.api_url }/songs/{ song[ "id" ] }/arrangements" ) ):
        if arrangement.get( "sourceId" ) == self.source_id:
          print( f"Deleting arrangement { arrangement[ "id" ] } of song { song[ "id" ] }." )
          if result := self.delete( f"{ self.api_url }/songs/{ song[ "id" ] }/arrangements/{ arrangement[ "id" ] }" ):
            pass
          else:
            raise ConnectionError( f"Failed to delete arrangement { arrangement[ "id" ] } of song { song[ "id" ] }: { result.status_code } - { result.text }" )
        else:
          delete_song = False
        
      if delete_song:
        print( f"Deleting song { song[ "id" ] } - { song[ "name" ] }." )
        if result := self.delete( f"{ self.api_url }/songs/{ song[ "id" ] }" ):
          pass
        else:
          raise ConnectionError( f"Failed to delete song { song[ "id" ] }: { result.status_code } - { result.text }" )

if __name__ == "__main__":

  import argparse
  import yaml

  defaults = dict()
  for path in ( os.path.expanduser( "~/.church-tools.yml" ), ):
    if os.path.isfile( path ):
      try:
        with open( path, "r", ) as config_file:
          for key, value in yaml.safe_load( config_file ).items():
            defaults[ key ] = value
      except FileNotFoundError:
        pass

  parser = argparse.ArgumentParser( description="Manage a ChurchTools song database." )
  parser.add_argument( "-u", "--api-url", type=str, help="ChurchTools API URL", required=( "api_url" not in defaults ), metavar="URL" )
  auth_group = parser.add_mutually_exclusive_group( required=( "api_token" not in defaults and "user" not in defaults ) )
  auth_group.add_argument( "-t", "--api-token", type=str, help="ChurchTools API token", metavar="TOKEN" )
  auth_group.add_argument( "--user", type=str, help="ChurchTools User Name", metavar="USER" )
  parser.set_defaults( **defaults )

  sub_parsers = parser.add_subparsers( dest="command" )

  import_parser = sub_parsers.add_parser( "import", help="Import .sng files into ChurchTools." )
  import_parser.add_argument( "--source_id", type=int, help="Source ID for imported arrangements", metavar="ID" )
  import_parser.add_argument( "--attachment_mode", type=AttachmentMode, choices=list( AttachmentMode ), default="skip" )
  import_parser.add_argument( "source", type=str, default=".", nargs="+" )
  import_parser.set_defaults( **defaults )

  delete_parser = sub_parsers.add_parser( "delete", help="Delete all imported songs from ChurchTools." )
  delete_parser.add_argument( "--source_id", type=int, help="Source ID of imported arrangements.", required=( "source_id" not in defaults ), metavar="ID" )
  delete_parser.set_defaults( **defaults )

  test_parser = sub_parsers.add_parser( "test", help="Test the ChurchTools connection." )

  arguments = parser.parse_args()

  match arguments.command:

    case "import":
      with ChurchToolsSession( arguments.api_url, api_token=arguments.api_token, user=arguments.user ) as session:

        session.source_id = arguments.source_id

        def do_import( path ):
          if song := SongBeamer.read_song( path ):
            if ct_song := session.import_song( song ):
              if ct_arrangement := session.import_arrangement( song, ct_song ):
                session.import_attachment( song, ct_arrangement, mode=arguments.attachment_mode )
                session.set_default_arrangement( ct_song[ "id" ], ct_arrangement[ "id" ] )

        for source in arguments.source:
          if os.path.isdir( source ):
            for file in os.scandir( source ):
              if file.is_file() and file.name.endswith( ".sng" ):
                do_import( file.path )
          else:
            do_import( source )

    case "delete":
      with ChurchToolsSession( arguments.api_url, api_token=arguments.api_token, user=arguments.user ) as session:
        session.source_id = arguments.source_id
        session.delete_imported_songs()
    
    case "test":
      with ChurchToolsSession( arguments.api_url, api_token=arguments.api_token, user=arguments.user ) as session:
        if result := session.get( f"{ session.api_url }/info" ):
          info = result.json()
          print( f"Connected to ChurchTools { info[ "version" ] } of '{ info[ "siteName" ] }'." )
        else:
          raise ConnectionError( f"Failed to get ChurchTools info: { result.status_code } - { result.text }" )
