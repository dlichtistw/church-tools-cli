#!/usr/bin/env python3

import argparse
import os

def try_get_title( path: os.PathLike, encoding: str ) -> str | None:
  with open( path, "r", encoding=encoding ) as file:
    for line in file:
      match line.split( "=", 1 ):
        case [ "#Title", value ]:
          return value.strip()

def get_title( path: os.PathLike ) -> str | None:
  try:
    return try_get_title( path, "utf8" )
  except UnicodeDecodeError:
    return try_get_title( path, "latin1" )

if __name__ == "__main__":

  parser = argparse.ArgumentParser( description="Find duplicate song titles in .sng files." )
  parser.add_argument( "directory", nargs="?", default=".", help="Directory to scan for .sng files (default: current directory)" )
  arguments = parser.parse_args()

  titles: dict[ str, list[ str ] ] = {}

  for path in os.scandir( arguments.directory ):
    if path.is_file() and path.name.endswith( ".sng" ):
      if title := get_title( path ):
        titles.setdefault( title.casefold(), [] ).append( path.name )
  
  for title, files in titles.items():
    if len( files ) > 1:
      print( f"Duplicate title: { title }" )
      for file in files:
        print( f"  - { file }" )
