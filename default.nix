{
  lib,
  python3Packages,
}:
python3Packages.buildPythonApplication {
  pname = "yt-transcripts";
  version = "0.1.0";
  pyproject = true;
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./LICENSE
      ./README.md
      ./pyproject.toml
      ./src
    ];
  };
  build-system = [ python3Packages.hatchling ];
  dependencies = [ python3Packages.yt-dlp ];
  # The yt-dlp extras are optional speedups; Nixpkgs' yt-dlp lacks some.
  pythonRelaxDeps = [ "yt-dlp" ];
  pythonImportsCheck = [ "yt_transcripts.web" ];
  meta = {
    description = "Turn YouTube videos into HTML reports";
    homepage = "https://github.com/lkollar/yt-transcripts";
    license = lib.licenses.mit;
    mainProgram = "yt-report-web";
  };
}
