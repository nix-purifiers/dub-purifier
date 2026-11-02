# SPDX-License-Identifier: MIT
{ serve-d }:
serve-d.overrideAttrs (old: {
  patches = (old.patches or [ ]) ++ [ ./serve-d.patch ];
})
