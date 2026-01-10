import types, typing

type_map: dict[ str, type ] = {
  "string": str,
  "null": types.NoneType,
  "integer": int,
}

def python_types( type_names: str | typing.Iterable[ str ] ) -> tuple[ type, ... ]:
  if isinstance( type_names, str ):
    return python_types( ( type_names, ) )
  else:
    return tuple( type_map[ t ] for t in type_names )

def sanitize( value, schema: dict ):

  if any_of := schema.get( "anyOf", [] ):
    for alternative in any_of:
      try:
        return sanitize( value, alternative )
      except ValueError:
        pass
    else:
      raise ValueError( f"Value '{ value }' does not match any of the allowed schemas." )
  
  if types := python_types( schema.get( "type", [] ) ):
    if not isinstance( value, types ):
      for t in types:
        try:
          value = t( value )
        except:
          continue
        break
      else:
        raise ValueError( f"Value '{ value }' does not match any of the allowed types." )
  
  if isinstance( value, str ):
    if enums := schema.get( "enum", [] ):
      if value not in enums:
        raise ValueError( f"Value '{ value } is not in the list of allowed values." )
    if lower := schema.get( "minLength" ):
      if len( value ) < lower:
        raise ValueError( f"Value '{ value }' is too short." )
    if upper := schema.get( "maxLength" ):
      if len( value ) > upper:
        value = value[ :upper-1 ] + "…"
  
  return value
