#!/usr/bin/env bash
# Copy nanopet to the board over one ssh connection (Dropbear has no SFTP).
#   usage: ./deploy.sh [user@host]
set -euo pipefail
BOARD=${1:-root@192.168.29.120}
DEST=/opt/nanopet
cd "$(dirname "$0")"
[ -f assets/font.npz ] || python3 tools/make_font.py
tar -cf - *.py assets/font.npz |
	ssh "$BOARD" "mkdir -p $DEST && tar -xf - -C $DEST"
echo "Deployed to $BOARD:$DEST"
echo "  ssh -t $BOARD python3 $DEST/demo_face.py           # live face, keyboard keys"
echo "  ssh $BOARD python3 $DEST/demo_face.py --bench      # render speed"
