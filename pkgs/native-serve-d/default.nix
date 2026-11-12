# SPDX-License-Identifier: MIT
{
  serve-d,
  python3,
  ldc,
  runtimeShell,
}:
serve-d.overrideAttrs (old: {
  patches = (old.patches or [ ]) ++ [ ./serve-d.patch ];
  postConfigure = (old.postConfigure or "") + ''
    workspace="$DUB_HOME/packages/workspace-d/3.7.0/workspace-d"
    install -m644 ${./process_lifecycle.d} "$workspace/source/workspaced/process_lifecycle.d"
    ${python3}/bin/python3 ${./patch-process-lifecycle.py} "$workspace"
  '';
  postCheck = (old.postCheck or "") + ''
    ${ldc}/bin/ldc2 -unittest -main ${./process_lifecycle.d} -of="$TMPDIR/process-lifecycle-tests"
    PURIFIER_TEST_SHELL=${runtimeShell} "$TMPDIR/process-lifecycle-tests"
  '';
})
