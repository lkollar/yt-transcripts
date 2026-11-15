{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.yt-transcripts;
  port = toString cfg.port;
in
{
  options.services.yt-transcripts = {
    enable = lib.mkEnableOption "YouTube report web UI";
    user = lib.mkOption {
      type = lib.types.str;
      description = "User owning the Claude login.";
    };
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../default.nix { };
    };
    claudePackage = lib.mkOption {
      type = lib.types.package;
      default = pkgs.claude-code;
    };
    model = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Model passed to claude; null uses the CLI's default.";
    };
    port = lib.mkOption {
      type = lib.types.port;
      default = 8765;
      description = "Port on 127.0.0.1. The UI has no login: expose it privately.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = builtins.hasAttr cfg.user config.users.users;
        message = "yt-transcripts.user must name an existing user";
      }
    ];
    users.users.${cfg.user}.linger = true;
    systemd.user.services.yt-transcripts = {
      description = "YouTube report web UI";
      wantedBy = [ "default.target" ];
      unitConfig.ConditionUser = cfg.user;
      path = [
        cfg.claudePackage
        # yt-dlp needs a JS runtime to solve YouTube player challenges.
        pkgs.nodejs
      ];
      environment.PYTHONUNBUFFERED = "1";
      serviceConfig = {
        Type = "simple";
        ExecStart = lib.concatStringsSep " " (
          [
            "${cfg.package}/bin/yt-report-web"
            "--port ${port}"
            "--out-dir %S/yt-transcripts/reports"
          ]
          ++ lib.optional (cfg.model != null) "--model ${lib.escapeShellArg cfg.model}"
        );
        StateDirectory = "yt-transcripts";
        StateDirectoryMode = "0700";
        Restart = "on-failure";
        RestartSec = 10;
        TimeoutStopSec = 15;
        KillMode = "control-group";
        UMask = "0077";
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = [
          "-%h/.claude"
          "-%h/.claude.json"
          "-%h/.cache"
        ];
        RestrictAddressFamilies = [
          "AF_UNIX"
          "AF_INET"
          "AF_INET6"
        ];
      };
    };
  };
}
