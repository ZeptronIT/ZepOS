# The live session's only job is the smoke run.
#
# Guarded on tty1 rather than run unconditionally: the image also gets
# logged into from the harness's rescue paths and from a plain `login` on
# another VT while a run is being watched, and a second Hyprland trying
# to take the same seat would turn a clean failure into an unreadable
# one.
#
# ZEPOS_SMOKE_ENTERED stops the guard from firing twice inside one
# session - `bash -l` from the smoke run's own shell would otherwise
# start the run again from inside itself.
if [[ "$(tty)" == /dev/tty1 && -z "${ZEPOS_SMOKE_ENTERED:-}" ]]; then
    export ZEPOS_SMOKE_ENTERED=1
    exec /usr/local/bin/zepos-smoke
fi
