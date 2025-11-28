#!/usr/bin/env python3

import datetime
import requests
import os, sys
import enum

class Song:

  title: str | None = None
  key: str | None = None
  author: str | None = None
  copyright: str | None = None
  ccli: int | None = None
  categories: list[ str ] = []
  file_name: str

  def __init__( self, file_name: str ):
    self.file_name = file_name

def dict_path( data: dict, *keys: str, default=None ):
  for key in keys:
    if key in data:
      data = data[ key ]
    else:
      return default
  return data

def try_read_song( path: str, encoding: str ) -> Song | None:

  with open( path, "r", encoding=encoding ) as file:

    song = Song( path )

    for line in file:
      match line.split( "=", 1 ):
        case [ "#Title", value ]:
          song.title = value.strip()
        case [ "#Key", value ]:
          song.key = value.strip()
        case [ "#Author", value ]:
          song.author = value.strip()
        case [ "#(c)", value ]:
          song.copyright = value.strip()
        case [ "#CCLI", value ]:
          try:
            song.ccli = int( value.strip() )
          except ValueError:
            print( f"Invalid CCLI number: { value.strip() }", file=sys.stderr )
        case [ "#Categories", value ]:
          song.categories = [ category.strip() for category in value.split( "," ) ]
  
    if song.title:
      return song

def read_song( path: str ) -> Song | None:
  try:
    return try_read_song( path, "utf8" )
  except UnicodeDecodeError:
    return try_read_song( path, "latin1" )

def has_more_pages( result: dict ) -> bool:
  if pagination := dict_path( result, "meta", "pagination" ):
    return pagination.get( "current", 0 ) < pagination.get( "lastPage", 0 )
  else:
    return False
  
def collect_pages( session: requests.Session, template: requests.Request ) -> list:
  result = session.send( session.prepare_request( template ) )
  if result:
    json = result.json()
    pages: list = json[ "data" ]

    while has_more_pages( json ):
      template.params[ "page" ] = json[ "meta" ][ "pagination" ][ "current" ] + 1
      result = session.send( session.prepare_request( template ) )
      if result:
        json = result.json()
        pages.extend( json[ "data" ] )
      else:
        raise ConnectionError( f"Faile to load additional pages: { result.status_code } - { result.text }" )
    
    return pages
  
  else:
    raise ConnectionError( f"Failed to load data: { result.status_code } - { result.text }" )

class Ambiguous:
  pass

class AttachmentMode( enum.Enum ):
  ADD = "add"
  SKIP = "skip"
  REPLACE = "replace"

  def __str__( self ) -> str:
    return self.value

class ChurchToolsSession( requests.Session ):

  api_url: str

  source_id: int | None = None
  arrangement_name: str = "SongBeamer"
  song_category: int = 0

  def __init__( self, api_url: str, api_token: str ):
    super().__init__()

    self.api_url = api_url

    self.headers.update( { "Authorization": f"Login { api_token }" } )
    if result := self.get( f"{ self.api_url }/whoami" ):
      data = result.json()[ "data" ]
      print( f"Authenticated as { data[ "firstName" ] } { data[ "lastName" ] } (ID: { data[ "id" ] })." )
    else:
      raise ConnectionError( f"Failed to authenticate: { result.status_code } - { result.text }." )

    if result := self.get( f"{ self.api_url }/csrftoken" ):
      if token := result.json().get( "data" ):
        self.headers.update( { "CSRF-Token": token } )
      else:
        raise ConnectionError( "Failed to obtain CSRF token: No token in response." )
    else:
      raise ConnectionError( f"Failed to obtain CSRF token: { result.status_code } - { result.text }" )

  def match_arrangement( self, song: Song, arrangements: list[ dict ] ) -> dict | None:
    for arrangement in arrangements:
      if self.source_id is None or arrangement.get( "sourceId" ) == self.source_id:
        for file in arrangement.get( "files", [] ):
          if file.get( "name" ) == os.path.basename( song.file_name ):
            return arrangement

  def match_song( self, song: Song, candidates: list[ dict ] ) -> dict | Ambiguous | None:

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
    
  def import_song( self, song: Song ) -> dict | None:

    songs = collect_pages( self, requests.Request( "GET", self.api_url + "/songs", params={ "name": song.title } ) )
    for s in songs:
      if "arrangements" not in s:
        s[ "arrangements" ] = collect_pages( self, requests.Request( "GET", f"{ self.api_url }/songs/{ s[ "id" ] }/arrangements" ) )

    match self.match_song( song, songs ):
      case dict() as existing:
        print( f"Updating existing song: { existing[ "id" ] } - { existing[ "name" ] }" )

        update = { k: v for k, v in existing.items() if k in [ "name", "author", "ccli", "copyright" ] }
        update[ "categoryId" ] = existing[ "category" ][ "id" ]
      
        if song.ccli:
          update[ "ccli" ] = song.ccli
    
        if song.author:
          update[ "author" ] = song.author

        if song.copyright:
          update[ "copyright" ] = song.copyright
        
        if result := self.put( f"{ self.api_url }/songs/{ existing[ "id" ] }", json=update ):
          return existing
        else:
          raise ConnectionError( f"Failed to update song { existing[ "id" ] }: { result.status_code } - { result.text }" )
    
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

  def import_arrangement( self, song: Song, ct_song: dict ) -> dict:

    match self.match_arrangement( song, ct_song.get( "arrangements", [] ) ):
      case dict() as existing:
        print( f"Updating existing arrangement { existing[ "id" ] } for song id { ct_song[ "id" ] }." )

        update = { k: v for k, v in existing.items() if k in [ "beat", "duration", "key", "name", "sourceId", "tempo" ] }
        update[ "description" ] = f"Updated from '{ os.path.basename( song.file_name ) }' on { datetime.date.today().isoformat() }."

        if song.key:
          update[ "key" ] = song.key

        if self.source_id and "sourceId" not in update:
          update[ "sourceId" ] = self.source_id

        if result := self.put( f"{ self.api_url }/songs/{ ct_song[ "id" ] }/arrangements/{ existing[ "id" ] }", json=update ):
          return existing
        else:
          raise ConnectionError( f"Failed to update arrangement { existing[ "id" ] } of song { ct_song[ "id" ] }: { result.status_code } - { result.text }" )
      
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

  def import_attachment( self, song: Song, arrangement: dict, mode: AttachmentMode = AttachmentMode.SKIP ):

    if mode != AttachmentMode.ADD:

      arrangement[ "files" ] = collect_pages( self, requests.Request( "GET", f"{ self.api_url }/files/song_arrangement/{ arrangement[ "id" ] }" ) )
    
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

    for song in collect_pages( self, requests.Request( "GET", self.api_url + "/songs", params={ "sourceId": self.source_id } ) ):

      delete_song = True

      for arrangement in collect_pages( self, requests.Request( "GET", f"{ self.api_url }/songs/{ song[ "id" ] }/arrangements" ) ):
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
  parser.add_argument( "-t", "--api-token", type=str, help="ChurchTools API token", required=( "api_token" not in defaults ), metavar="TOKEN" )
  parser.set_defaults( **defaults )

  sub_parsers = parser.add_subparsers( dest="command" )

  import_parser = sub_parsers.add_parser( "import", help="Import .sng files into ChurchTools." )
  import_parser.add_argument( "--source_id", type=int, help="Source ID for imported arrangements", metavar="ID" )
  import_parser.add_argument( "--attachment_mode", type=AttachmentMode, choices=list( AttachmentMode ), default="skip" )
  import_parser.add_argument( "source_directory", type=str, default=".", nargs="?" )
  import_parser.set_defaults( **defaults )

  delete_parser = sub_parsers.add_parser( "delete", help="Delete all imported songs from ChurchTools." )
  delete_parser.add_argument( "--source_id", type=int, help="Source ID of imported arrangements.", required=( "source_id" not in defaults ), metavar="ID" )
  delete_parser.set_defaults( **defaults )

  test_parser = sub_parsers.add_parser( "test", help="Test the ChurchTools connection." )


  arguments = parser.parse_args()

  match arguments.command:

    case "import":
      with ChurchToolsSession( arguments.api_url, arguments.api_token ) as session:

        session.source_id = arguments.source_id

        for file in os.scandir( arguments.source_directory ):
          if file.is_file() and file.name.endswith( ".sng" ):
            if song := read_song( file.path ):
              if ct_song := session.import_song( song ):
                if ct_arrangement := session.import_arrangement( song, ct_song ):
                  session.import_attachment( song, ct_arrangement, mode=arguments.attachment_mode )
                  session.set_default_arrangement( ct_song[ "id" ], ct_arrangement[ "id" ] )

    case "delete":
      with ChurchToolsSession( arguments.api_url, arguments.api_token ) as session:
        session.source_id = arguments.source_id
        session.delete_imported_songs()
    
    case "test":
      with ChurchToolsSession( arguments.api_url, arguments.api_token ) as session:
        if result := session.get( f"{ session.api_url }/info" ):
          info = result.json()
          print( f"Connected to ChurchTools { info[ "version" ] } of '{ info[ "siteName" ] }'." )
        else:
          raise ConnectionError( f"Failed to get ChurchTools info: { result.status_code } - { result.text }" )
