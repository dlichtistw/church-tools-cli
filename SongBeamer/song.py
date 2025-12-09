class Song:

  def __init__( self, title: str ) -> None:
    self.title: str = title
    self.key: str | None = None
    self.author: str | None = None
    self.copyright: str | None = None
    self.ccli: str | None = None
    self.categories: list[ str ] = []

class ImportedSong( Song ):
    
  def __init__( self, title: str, file_name: str ) -> None:
    super().__init__( title )
    self.file_name: str = file_name

def try_read_song( path: str, encoding: str ) -> ImportedSong | None:

  with open( path, "r", encoding=encoding ) as file:

    song = ImportedSong( "", path )

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
          song.ccli = value.strip()
        case [ "#Categories", value ]:
          song.categories = [ category.strip() for category in value.split( "," ) ]
  
    if song.title:
      return song

def read_song( path: str ) -> ImportedSong | None:
  try:
    return try_read_song( path, "utf_8_sig" )
  except UnicodeDecodeError:
    return try_read_song( path, "latin1" )

