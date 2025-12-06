#!/usr/bin/env python3

import requests
import argparse

api_url = "https://efg-hst.church.tools/api/"
api_token = "GupcVBAaos0PIW4I3pC0IdkeKg8UffBoqH2i2HdXkRPEwnyohWmxW0xnmLYJ1fvZiu63fxBNP3x6R1yVkWu0nDItvf6fFByqBx2XaofUlDEuSlE8sWEDdfdn5D6GGZoGibBIFRdqp2uGDWYyuB5Ld94PpGnBcjkzXeUXnUV32wTxUbO6YpqzD4wwNscFzMt78xRus9IkNi1MhNDDDy279krjV0oXp2q1G7Nu0YlPx0G7QcqAYqpA7kccr65x6mf5"

def check_result( result: requests.Response ):
  if not result:
    print( f"Status: { result.status_code } - { result.text }" )
  return result

def get_info( url: str ):
  result = requests.get( url + "info" )
  if check_result( result ):
    json = result.json()
    print( json[ "siteName" ] )
    print( f"ChurchTools Version: { json[ "version" ] }" )

def get_whoami( url: str, token: str | None = None ):
  headers = {}
  if token:
    headers[ "Authorization" ] = f"Login { token }"
  
  result = requests.get( url + "whoami", headers=headers )
  if check_result( result ):
    json = result.json()
    print( f"{ json[ "data" ][ "firstName" ] } { json[ "data" ][ "lastName" ] } ({ json[ "data" ][ "id" ] })" )

def list_songs( songs: list[ dict ] ):
  for song in songs:
    print( f"{ song[ "id" ] }: { song[ "name" ] }" )

def has_more_pages( result: dict ) -> bool:
  if result[ "meta" ] and result[ "meta" ][ "pagination" ]:
    pagination = result[ "meta" ][ "pagination" ]
    return pagination[ "current" ] < pagination[ "lastPage" ]
  else:
    return False
  
def next_page( result: dict ) -> int | None:
  if result[ "meta" ] and result[ "meta" ][ "pagination" ]:
    pagination = result[ "meta" ][ "pagination" ]
    if pagination[ "current" ] < pagination[ "lastPage" ]:
      return pagination[ "current" ] + 1
  return None

def get_songs( url: str, token: str ):
  result = requests.get( url + "songs", headers={ "Authorization": f"Login { token }" } )
  if check_result( result ):
    session = result.cookies.get( "ChurchTools_ct_efg-hst" )
    json = result.json()

    list_songs( json[ "data" ] )

    next = next_page( json )
    while next:
      result = requests.get( f"{ url }songs?page={ next }", cookies={ "ChurchTools_ct_efg-hst": str( session ) } )
      if ( check_result( result ) ):
        json = result.json()
        list_songs( json[ "data" ] )
        next = next_page( json )
      else:
        return

if __name__ == "__main__":

  parser = argparse.ArgumentParser()
  parser.add_argument( "-u", "--url", help="API URL", default=api_url )
  parser.add_argument( "-t", "--token", help="API Token", default=api_token )

  subparsers = parser.add_subparsers( dest="command" )

  subparsers.add_parser( "info", help="Get API info" )
  
  subparsers.add_parser( "whoami", help="Get current user info" )

  subparsers.add_parser( "songs", help="List all songs" )

  arguments = parser.parse_args()
  match arguments.command:
    case "whoami":
      get_whoami( arguments.url, arguments.token )
    case "songs":
      get_songs( arguments.url, arguments.token )
    case "info", _:
      get_info( arguments.url )
