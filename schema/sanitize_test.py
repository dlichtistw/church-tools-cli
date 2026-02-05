from .sanitize import python_types, sanitize

import types
import pytest


class TestPythonTypes:

  def test_empty( self ):
    assert python_types( [] ) == tuple()

  @pytest.mark.parametrize( "type_name,type", [ ( "string", str ), ( "integer", int ), ( "null", types.NoneType ) ] )
  def test_single( self, type_name: str, type: type ):
    assert python_types( type_name ) == ( type, )
    assert python_types( [ type_name ] ) == ( type, )

  def test_multiple( self ):
    assert python_types( [ "string", "integer", "null" ] ) == ( str, int, types.NoneType )

  def test_invalid( self ):
    with pytest.raises( KeyError ):
      python_types( "invalid type" )


class TestSanitize:

  def test_string_length( self ):

    schema = { "type": "string", "minLength": 3, "maxLength": 5 }

    with pytest.raises( ValueError ):
      sanitize( "ab", schema )
    assert sanitize( "abc", schema ) == "abc"
    assert sanitize( "abcde", schema ) == "abcde"
    assert sanitize( "abcdef", schema ) == "abcd…"

  def test_string_enum( self ):

    schema = { "type": "string", "enum": [ "red", "green", "blue" ] }

    assert sanitize( "red", schema ) == "red"
    assert sanitize( "green", schema ) == "green"
    assert sanitize( "blue", schema ) == "blue"

    with pytest.raises( ValueError ):
      sanitize( "yellow", schema )

  def test_type_conversion( self ):

    schema = { "type": [ "null", "integer" ] }

    assert sanitize( None, schema ) is None
    assert sanitize( 123, schema ) == 123
    assert sanitize( 45.67, schema ) == 45

    with pytest.raises( ValueError ):
      sanitize( "abc", schema )

  def test_any_of( self ):

    schema = {
      "anyOf": [
        { "type": "string", "enum": [ "red", "green", "blue" ] },
        { "type": "integer" },
        { "type": "string", "minLength": 7, "maxLength": 9 },
      ]
    }

    assert sanitize( "green", schema ) == "green"
    assert sanitize( "12345", schema ) == 12345
    assert sanitize( "abcdefghijk", schema ) == "abcdefgh…"

    with pytest.raises( ValueError ):
      sanitize( "yellow", schema )
