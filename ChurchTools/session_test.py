from .session import join_path, has_more_pages, Session


class TestHasMorePages:

  def test_no_pagination( self ):
    assert not has_more_pages( {} )
    assert not has_more_pages( { "meta": {} } )

  def test_invalid_pagination( self ):
    assert not has_more_pages( { "meta": { "pagination": {} } } )
    assert not has_more_pages( { "meta": { "pagination": { "current": 1 } } } )

  def test_no_more_pages( self ):
    assert not has_more_pages( { "meta": { "pagination": { "current": 1, "lastPage": 1 } } } )
    assert not has_more_pages( { "meta": { "pagination": { "current": 2, "lastPage": 0 } } } )

  def test_more_pages( self ):
    assert has_more_pages( { "meta": { "pagination": { "current": 1, "lastPage": 2 } } } )
    assert has_more_pages( { "meta": { "pagination": { "lastPage": 3 } } } )


class TestJoinPath:

  def test_base_only( self ):
    base = "protocol://host/path"
    assert join_path( base ) == base

  def test_multi_segments( self ):
    base = "protocol://host/path"
    segments = [ "to", "resource" ]
    assert join_path( base, *segments ) == "/".join( [ base, *segments ] )

  def test_separator_elision( self ):
    base = "protocol://host/path/"
    segments = [ "to/", "/some", "/resource" ]
    assert join_path( base, *segments ) == "".join( [ base, *segments ] )

  def test_custom_separator( self ):
    base = "protocol://host/path/"
    separator = "~"
    segments = [ "to" + separator, "some" + separator, separator + "important" + separator, separator + "resource" ]
    assert join_path( base, *segments, separator=separator ) == separator.join( [ base, "".join( segments ) ] )


class TestSession:

  def test_init( self ):

    url = "test://church.tools.local/"
    token = "secret-token"

    session = Session( url, token )

    assert session.api_url == url
    assert session.headers.get( "Authorization" ) == f"Login { token }"
    assert session.default_page_size is None

  def test_endpoint_url( self ):

    url = "test://church.tools.local/"
    session = Session( url )
    endpoint = "some/endpoint"

    assert session.endpoint_url( endpoint ) == url + endpoint
