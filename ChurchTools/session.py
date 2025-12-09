import requests
import requests.adapters

def has_more_pages( result: dict ) -> bool:
  if pagination := result.get( "meta", {} ).get( "pagination" ):
    return pagination.get( "current", 0 ) < pagination.get( "lastPage", 0 )
  else:
    return False
  
class Session( requests.Session ):

  default_page_size: int | None = None

  def __init__( self, api_url: str, api_token: str ) -> None:
    super().__init__()

    self.api_url: str = api_url

    self.headers.update( { "Authorization": f"Login { api_token }" } )

    retries = requests.adapters.Retry( total=5, backoff_factor=1, allowed_methods=None, status_forcelist={ 429, } )
    self.mount( self.api_url, requests.adapters.HTTPAdapter( max_retries=retries ) )

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
