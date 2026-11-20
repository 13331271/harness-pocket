"""Align and locally sign a completed APK; signing secrets never enter artifacts."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess


def run(arguments, env):
    # Inherit stdio; do not create child-process capture pipes or print passwords.
    subprocess.run([str(value) for value in arguments], env=env, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--java-home", required=True, type=Path)
    parser.add_argument("--build-tools", required=True, type=Path)
    parser.add_argument("--private-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.input.resolve(strict=True)
    destination = args.output.resolve()
    private = args.private_dir.resolve()
    if source == destination or destination.exists():
        raise FileExistsError("Refusing to overwrite an input or existing APK")
    destination.parent.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)
    keystore = private / "harness-pocket-local.p12"
    settings = private / "signing-secret.json"
    env = os.environ.copy()
    env["JAVA_HOME"] = str(args.java_home.resolve(strict=True))
    env["TEMP"] = env["TMP"] = str(private)
    env["TMPDIR"] = str(private)
    if settings.exists():
        secret = json.loads(settings.read_text(encoding="utf-8"))
        if not keystore.is_file():
            raise FileNotFoundError("Local signing identity is incomplete")
    else:
        if keystore.exists():
            raise FileExistsError("A signing keystore already exists without its local secret")
        secret = {"alias": "harness-pocket-local", "password": secrets.token_urlsafe(36)}
        env["POCKET_SIGN_PASSWORD"] = secret["password"]
        run([args.java_home / "bin/keytool.exe", "-genkeypair", "-noprompt",
             "-storetype", "PKCS12", "-keystore", keystore,
             "-storepass:env", "POCKET_SIGN_PASSWORD",
             "-keypass:env", "POCKET_SIGN_PASSWORD", "-alias", secret["alias"],
             "-keyalg", "RSA", "-keysize", "3072", "-validity", "3650",
             "-dname", "CN=Harness Pocket Local Build, OU=Personal Build, O=Local, C=CN"], env)
        settings.write_text(json.dumps(secret) + "\n", encoding="utf-8")
        os.chmod(settings, 0o600)
        os.chmod(keystore, 0o600)
    env["POCKET_SIGN_PASSWORD"] = secret["password"]
    aligned = private / ("aligned-" + destination.stem + ".apk")
    if aligned.exists():
        raise FileExistsError("An aligned intermediate already exists; do not overwrite it")
    run([args.build_tools / "zipalign.exe", "-P", "16", "-f", "4", source, aligned], env)
    # Invoke the reviewed tool JAR directly to avoid cmd.exe/batch quoting issues.
    run([args.java_home / "bin/java.exe", "-Xmx1024m", "-jar",
         args.build_tools / "lib/apksigner.jar", "sign", "--ks", keystore,
         "--ks-key-alias", secret["alias"], "--ks-pass", "env:POCKET_SIGN_PASSWORD",
         "--key-pass", "env:POCKET_SIGN_PASSWORD", "--v1-signing-enabled", "true",
         "--v2-signing-enabled", "true", "--v3-signing-enabled", "true",
         "--out", destination, aligned], env)
    run([args.java_home / "bin/java.exe", "-Xmx1024m", "-jar",
         args.build_tools / "lib/apksigner.jar", "verify", "--verbose", "--print-certs",
         destination], env)
    run([args.build_tools / "zipalign.exe", "-c", "-P", "16", "4", destination], env)
    print("Locally signed APK verified:", destination)
    print("Private signing identity remains outside all deliverables.")


if __name__ == "__main__":
    main()
