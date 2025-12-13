import requests
import getpass

def has_more_pages( result: dict ) -> bool:
  if pagination := result.get( "meta", {} ).get( "pagination" ):
    return pagination.get( "current", 0 ) < pagination.get( "lastPage", 0 )
  else:
    return False
  
def join_path( base: str, *segments: str, separator: str = "/" ) -> str:
  for s in segments:
    if not base.endswith( separator ) or not s.startswith( separator ):
      base += separator
    base += s
  return base
  
class Session( requests.Session ):

  default_page_size: int | None = None

  def __init__( self, api_url: str, api_token: str | None = None ) -> None:
    super().__init__()

    self.api_url: str = api_url

    if api_token:
      self.headers.update( { "Authorization": f"Login { api_token }" } )

  def endpoint_url( self, endpoint: str ) -> str:
    return join_path( self.api_url, endpoint )

  def login( self, username: str, password: str | None = None ):

    if not password:
      password = getpass.getpass( f"ChurchTools password for user '{ username }': " )
    
    if result := self.post( self.endpoint_url( "login" ), data={ "password": password, "username": username } ):
      pass
    else:
      raise ConnectionError( f"Failed to login to '{ self.api_url }' as user '{ username }': { result.status_code } - { result.text }" )

  def collect( self, template: requests.Request, *, page_size: int | None = None, start_page: int = 0 ) -> list:

    template.params[ "page" ] = start_page
    if limit := page_size or self.default_page_size:
      template.params[ "limit" ] = limit

    if result := self.send( self.prepare_request( template ) ):
      json = result.json()
      pages: list = json[ "data" ]

      while has_more_pages( json ):
        template.params[ "page" ] = json[ "meta" ][ "pagination" ][ "current" ] + 1
        if result := self.send( self.prepare_request( template ) ):
          json = result.json()
          pages.extend( json[ "data" ] )
        else:
          raise ConnectionError( f"Failed to load additional pages: { result.status_code } - { result.text }" )
      
      return pages
    
    else:
      raise ConnectionError( f"Failed to load data: { result.status_code } - { result.text }" )
