#!/bin/bash
CONTAINER_ALREADY_STARTED="CONTAINER_ALREADY_STARTED_PLACEHOLDER"
if [ ! -e $CONTAINER_ALREADY_STARTED ]; then
	cd /eq2emu
	wget ${MKCERT_URL}
	sudo mv ${MKCERT_FILE} /usr/bin/mkcert
	sudo chmod +x /usr/bin/mkcert
	wget ${PREMAKE5_PKG}
	tar -xzvf ${PREMAKE5_FILE}
	git clone ${RECAST_GIT}
	cp premake5 recastnavigation/RecastDemo
	cd recastnavigation/RecastDemo
	./premake5 gmake2
	# ### LOCAL PATCH: premake5 v5.0.0-beta2 emits "-Werror=All" (capital A)
	# into generated makefiles. Modern GCC rejects it ("no option '-WAll'"),
	# which breaks the Recast build and cascades into an unlinkable eq2world.
	# Stripping the flag keeps warnings visible but non-fatal. Remove this
	# patch once premake5 or recastnavigation upstream fixes the flag.
	# Tracked in docker/README.md under "Local patches".
	sed -i 's/-Werror=All//g' Build/gmake2/*.make
	cd Build/gmake2
	make
	cd /eq2emu
	git clone ${FMT_GIT}
	git clone ${EQ2SOURCE_GIT}
	git clone ${EQ2CONTENT_GIT}
	git clone ${EQ2MAPS_GIT}
	git clone ${EQ2DB_GIT}
	git clone ${EQ2DAWN_GIT}
	mkdir -p /eq2emu/eq2emu/server
	cd /eq2emu/eq2emu/source/LoginServer
	git pull
	make clean
	make -j$(nproc)
	cp login /eq2emu/eq2emu/server/
	cd /eq2emu/eq2emu/source/WorldServer
	git pull
	make clean
	make -j$(nproc)
	cp eq2world /eq2emu/eq2emu/server/
	cd /eq2emu/eq2emu-content
	cp -r ItemScripts Quests RegionScripts SpawnScripts Spells ZoneScripts /eq2emu/eq2emu/server/
	cd /eq2emu/eq2emu/server/
	sudo chmod -R 777 ItemScripts Quests RegionScripts SpawnScripts Spells ZoneScripts # allows eq2emu-editor container to write files
	cd /eq2emu/eq2emu-maps
	cp -r Maps Regions /eq2emu/eq2emu/server/
fi