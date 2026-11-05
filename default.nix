{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
}:
let
  python = python3.withPackages (ps: [ ps.yt-dlp ]);
in
stdenvNoCC.mkDerivation {
  pname = "yt-transcripts";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./fetch_transcript.py
      ./web.py
      ./yt_report.py
    ];
  };
  nativeBuildInputs = [ makeWrapper ];
  dontConfigure = true;
  dontBuild = true;
  installPhase = ''
    mkdir -p $out/bin $out/libexec/yt-transcripts
    cp *.py $out/libexec/yt-transcripts/
    makeWrapper ${python}/bin/python3 $out/bin/yt-transcripts-web \
      --add-flags $out/libexec/yt-transcripts/web.py
    makeWrapper ${python}/bin/python3 $out/bin/yt-report \
      --add-flags $out/libexec/yt-transcripts/yt_report.py
  '';
  meta = {
    description = "Turn YouTube videos into HTML reports";
    homepage = "https://github.com/lkollar/yt-transcripts";
    mainProgram = "yt-transcripts-web";
    platforms = [ "x86_64-linux" ];
  };
}
