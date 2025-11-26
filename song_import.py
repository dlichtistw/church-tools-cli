#!/usr/bin/env python3

import datetime
import requests
import os, sys
import enum
import argparse

api_url = None #TODO: Set your ChurchTools API URL here.
api_token = None #TODO: Set your API token here.

song_category = 0 # Unbekannt

arrangement_name = "SongBeamer"
arrangement_source = 3 # SongBeamer

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

def match_arrangement( song: Song, arrangements: list[ dict ] ) -> dict | None:
  for arrangement in arrangements:
    if arrangement.get( "sourceId" ) == arrangement_source:
      for file in arrangement.get( "files", [] ):
        if file.get( "name" ) == os.path.basename( song.file_name ):
          return arrangement

def match_song( song: Song, candidates: list[ dict ] ) -> dict | Ambiguous | None:

  for s in candidates:
    if match_arrangement( song, s.get( "arrangements", [] ) ):
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
  
def import_song( song: Song, session: requests.Session ) -> dict | None:

  songs = collect_pages( session, requests.Request( "GET", api_url + "/songs", params={ "name": song.title } ) )
  for s in songs:
    if "arrangements" not in s:
      s[ "arrangements" ] = collect_pages( session, requests.Request( "GET", f"{ api_url }/songs/{ s[ "id" ] }/arrangements" ) )

  match match_song( song, songs ):
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
      
      if result := session.put( f"{ api_url }/songs/{ existing[ "id" ] }", json=update ):
        return existing
      else:
        raise ConnectionError( f"Failed to update song { existing[ "id" ] }: { result.status_code } - { result.text }" )
  
    case None:
      print( f"Creating new song: { song.title }" )

      insert: dict = { "name": song.title, "categoryId": song_category }

      if song.ccli:
        insert[ "ccli" ] = song.ccli
      
      if song.author:
        insert[ "author" ] = song.author

      if song.copyright:
        insert[ "copyright" ] = song.copyright
      
      if result := session.post( api_url + "/songs", json=insert ):
        return result.json()[ "data" ]
      else:
        raise ConnectionError( f"Faile to create song: { result.status_code } - { result.text }" )
      
    case Ambiguous():
      print( f"Could not match song '{ song.title }'." )

def import_arrangement( song: Song, ct_song: dict, session: requests.Session ) -> dict:

  match match_arrangement( song, ct_song.get( "arrangements", [] ) ):
    case dict() as existing:
      print( f"Updating existing arrangement { existing[ "id" ] } for song id { ct_song[ "id" ] }." )

      update = { k: v for k, v in existing.items() if k in [ "beat", "duration", "key", "name", "sourceId", "tempo" ] }
      update[ "description" ] = f"Updated from '{ os.path.basename( song.file_name ) }' on { datetime.date.today().isoformat() }."

      if song.key:
        update[ "key" ] = song.key

      if arrangement_source and not update[ "sourceId" ]:
        update[ "sourceId" ] = arrangement_source

      if result := session.put( f"{ api_url }/songs/{ ct_song[ "id" ] }/arrangements/{ existing[ "id" ] }", json=update ):
        return existing
      else:
        raise ConnectionError( f"Failed to update arrangement { existing[ "id" ] } of song { ct_song[ "id" ] }: { result.status_code } - { result.text }" )
    
    case None:
      print( f"Creating new arrangement for song id { ct_song[ "id" ] }." )

      insert: dict = {
        "name": arrangement_name,
        "description": f"Created from '{ os.path.basename( song.file_name ) }' on { datetime.date.today().isoformat() }"
      }

      if arrangement_source:
        insert[ "sourceId" ] = arrangement_source

      if song.key:
        insert[ "key" ] = song.key

      if result := session.post( f"{ api_url }/songs/{ ct_song[ "id" ] }/arrangements", json=insert ):
        return result.json()[ "data" ]
      else:
        raise ConnectionError( f"Failed to create arrangement: { result.status_code } - { result.text }." )

def obtain_csrf_token( session: requests.Session ):
  if "CSRF-Token" not in session.headers:
    print( "Requsting CSRF token." )
    if result := session.get( f"{ api_url }/csrftoken" ):
      if token := result.json().get( "data" ):
        session.headers.update( { "CSRF-Token": token } )
      else:
        raise ConnectionError( "Failed to obtain CSRF token: No token in response." )
    else:
      raise ConnectionError( f"Failed to obtain CSRF token: { result.status_code } - { result.text }" )

class AttachmentMode( enum.Enum ):
  ADD = "add"
  SKIP = "skip"
  REPLACE = "replace"

  def __str__( self ) -> str:
    return self.value

def import_attachment( song: Song, arrangement: dict, session: requests.Session, mode: AttachmentMode = AttachmentMode.SKIP ):

  obtain_csrf_token( session )

  if mode != AttachmentMode.ADD:

    arrangement[ "files" ] = collect_pages( session, requests.Request( "GET", f"{ api_url }/files/song_arrangement/{ arrangement[ "id" ] }" ) )
  
    for file in arrangement.get( "files", [] ):
      if file.get( "name" ) == os.path.basename( song.file_name ):
        if mode == AttachmentMode.SKIP:
          print( f"Keeping existing attachment { file[ "id" ] } for arrangement { arrangement[ "id" ] }." )
          return
        elif mode == AttachmentMode.REPLACE:
          print( f"Deleting existing attachment { file[ "id" ] } for arrangement { arrangement[ "id" ] }." )
          if result := session.delete( f"{ api_url }/files/{ file[ "id" ] }" ):
            pass
          else:
            raise ConnectionError( f"Failed to delete attachment { file[ "id" ] }: { result.status_code } - { result.text }" )
    
  print( f"Uploading attachment '{ os.path.basename( song.file_name ) }' for arrangement { arrangement[ "id" ] }." )
  with open( song.file_name, "rb" ) as file:
    files = { "files[]": ( os.path.basename( song.file_name ), file ) }
    if result := session.post( f"{ api_url }/files/song_arrangement/{ arrangement[ "id" ] }", files=files ):
      return
    else:
      raise ConnectionError( f"Failed to upload attachment for arrangement { arrangement[ "id" ] }: { result.status_code } - { result.text }" )
  
  
def set_default_arrangement( song_id: int, arrangement_id: int, session: requests.Session ):
  if result := session.patch( f"{ api_url }/songs/{ song_id }/arrangements/{ arrangement_id }/default" ):
    return
  else:
    raise ConnectionError( f"Failed to set arrangement { arrangement_id } as default for song { song_id }: { result.status_code } - { result.text }" )

if __name__ == "__main__":

  parser = argparse.ArgumentParser( description="Import .sng song files into ChurchTools." )
  parser.add_argument( "--attachment-mode", type=AttachmentMode, choices=list( AttachmentMode ), default="skip" )
  parser.add_argument( "source-directory", type=str, default=".", nargs="?" )

  arguments = parser.parse_args()

  with requests.Session() as session:

    session.headers.update( { "Authorization": f"Login { api_token }" } )

    for file in os.scandir():
      if file.is_file() and file.name.endswith( ".sng" ):
        if song := read_song( file.path ):
          if ct_song := import_song( song, session ):
            if ct_arrangement := import_arrangement( song, ct_song, session ):
              import_attachment( song, ct_arrangement, session )
              set_default_arrangement( ct_song[ "id" ], ct_arrangement[ "id" ], session )

