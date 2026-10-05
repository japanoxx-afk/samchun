using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;

internal static class EditorUpgrade {
 static string Hash(byte[] data){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(data)).Replace("-","");}
 internal static bool IsSource(byte[] data){return Hash(data)=="FAA9BF7F9EE7BE3CB79FC92515233A279DD1DEA14F469C9EC5F8E5CF0E46F342";}
 internal static byte[] Apply(byte[] source) {
  if(!IsSource(source))throw new InvalidDataException("에디터 변환 원본 검증 실패");
  using(var resource=Assembly.GetExecutingAssembly().GetManifestResourceStream("editor-upgrade.bin")) {
   if(resource==null)throw new InvalidDataException("에디터 변환 데이터가 없습니다. 런처를 업데이트하세요.");
   using(var zip=new GZipStream(resource,CompressionMode.Decompress))using(var reader=new BinaryReader(zip)) {
    if(System.Text.Encoding.ASCII.GetString(reader.ReadBytes(5))!="EDUP1")throw new InvalidDataException("에디터 변환 형식 오류");
    int size=reader.ReadInt32();if(size!=5414912||source.Length<size)throw new InvalidDataException("에디터 변환 크기 오류");
    byte[] delta=reader.ReadBytes(size);if(delta.Length!=size||reader.Read()!=-1)throw new InvalidDataException("에디터 변환 데이터 손상");
    for(int i=0;i<size;i++)delta[i]^=source[i];
    if(Hash(delta)!="58D8D5399AB47BFB4D42B30C16642ED6E415CBC359025C75FD164E6131A5417D")throw new InvalidDataException("에디터 변환 결과 검증 실패");
    return delta;
   }
  }
 }
}
