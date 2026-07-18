#---------------------------------------------------------------------------------
.SUFFIXES:
#---------------------------------------------------------------------------------

ifeq ($(strip $(DEVKITPRO)),)
$(error "Please set DEVKITPRO in your environment. export DEVKITPRO=<path to>/devkitpro")
endif

TOPDIR ?= $(CURDIR)
include $(DEVKITPRO)/libnx/switch_rules

#---------------------------------------------------------------------------------
# TARGET is the name of the output
# BUILD is the directory where object files & intermediate files will be placed
# SOURCES is a list of directories containing source code
# INCLUDES is a list of directories containing header files
# ROMFS is the directory containing data to be added to RomFS (here: cacert.pem
#   for HTTPS certificate verification via libcurl/mbedtls)
#---------------------------------------------------------------------------------
TARGET		:=	SwitchCheatsDownloader
BUILD		:=	build
SOURCES		:=	source sqlite
INCLUDES	:=	source sqlite
ROMFS		:=	romfs

APP_TITLE   := Switch Cheats Scraper & Downloader
APP_AUTHOR  := DevCatSKZ
APP_VERSION := 2.1.3

# Einzige Quelle der Versionsnummer: wird als APP_VERSION-Makro in den Code
# durchgereicht (config.hpp: kAppVersion + kUserAgent) und von den
# devkitPro-Regeln fuer die .nacp verwendet.
DEFINES := -DAPP_VERSION=\"$(APP_VERSION)\"

# SQLite-Amalgamation (sqlite/sqlite3.c) fuer die Bibliotheks-Datenbank.
# Zugeschnitten auf die Switch: kein WAL/mmap/shm (newlib), kein dlopen,
# Temp-Dateien im RAM, single-threaded (DB wird NUR vom UI-Thread benutzt).
# Die DB wird ausschliesslich READ-ONLY mit dem "unix-none"-VFS geoeffnet
# (keine fcntl-Locks - auf libnx nicht implementiert).
DEFINES += -DSQLITE_THREADSAFE=0 -DSQLITE_OMIT_WAL -DSQLITE_OMIT_LOAD_EXTENSION \
           -DSQLITE_TEMP_STORE=3 -DSQLITE_MAX_MMAP_SIZE=0 \
           -DSQLITE_DEFAULT_MEMSTATUS=0 -DSQLITE_OMIT_DEPRECATED

#---------------------------------------------------------------------------------
# options for code generation
#---------------------------------------------------------------------------------
ARCH	:=	-march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIE

CFLAGS	:=	`$(PREFIX)pkg-config --cflags sdl2 SDL2_ttf SDL2_image minizip` -Wall -O2 -ffunction-sections \
			$(ARCH) $(DEFINES)

CFLAGS	+=	$(INCLUDE) -D__SWITCH__

CXXFLAGS	:= $(CFLAGS) -std=gnu++17

ASFLAGS	:=	-g $(ARCH)
LDFLAGS	=	-specs=$(DEVKITPRO)/libnx/switch.specs -g $(ARCH) -Wl,-Map,$(notdir $*.map)

LIBS	:=	-Wl,--start-group \
			`$(PREFIX)pkg-config --libs sdl2 SDL2_ttf SDL2_image minizip` \
			-lcurl -lmbedtls -lmbedx509 -lmbedcrypto -lz \
			-lnx \
			-Wl,--end-group

#---------------------------------------------------------------------------------
# list of directories containing libraries, this must be the top level containing
# include and lib
#---------------------------------------------------------------------------------
LIBDIRS	:= $(PORTLIBS) $(LIBNX)


#---------------------------------------------------------------------------------
# no real need to edit anything past this point unless you need to add additional
# rules for different file extensions
#---------------------------------------------------------------------------------
ifneq ($(BUILD),$(notdir $(CURDIR)))
#---------------------------------------------------------------------------------

export OUTPUT	:=	$(CURDIR)/$(TARGET)
export TOPDIR	:=	$(CURDIR)

export VPATH	:=	$(foreach dir,$(SOURCES),$(CURDIR)/$(dir))

export DEPSDIR	:=	$(CURDIR)/$(BUILD)

CFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
CPPFILES	:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
SFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))

#---------------------------------------------------------------------------------
# use CXX for linking C++ and libEGL dependent projects
#---------------------------------------------------------------------------------
export LD	:=	$(CXX)

export OFILES_SRC	:=	$(CPPFILES:.cpp=.o) $(CFILES:.c=.o) $(SFILES:.s=.o)
export OFILES 	:=	$(OFILES_SRC)

export INCLUDE	:=	$(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir)) \
			$(foreach dir,$(LIBDIRS),-I$(dir)/include) \
			-I$(CURDIR)/$(BUILD)

export LIBPATHS	:=	$(foreach dir,$(LIBDIRS),-L$(dir)/lib)

ifneq ($(ROMFS),)
	export NROFLAGS += --romfsdir=$(CURDIR)/$(ROMFS)
endif

# App-Icon (256x256 JPEG) einbetten, falls vorhanden - erzeugt aus dem
# offiziellen App-Logo der Windows-Software (app_icon.png), siehe README.
ifneq (,$(wildcard $(CURDIR)/icon.jpg))
	export APP_ICON := $(CURDIR)/icon.jpg
	export NROFLAGS += --icon=$(APP_ICON)
endif

export APP_JSON :=
export NROFLAGS += --nacp=$(CURDIR)/$(TARGET).nacp

.PHONY: $(BUILD) clean all

#---------------------------------------------------------------------------------
all: $(BUILD)

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@cd $(BUILD) && $(MAKE) --no-print-directory -f "$(CURDIR)/Makefile"

#---------------------------------------------------------------------------------
clean:
	@echo clean ...
	@rm -fr $(BUILD) $(TARGET).nro $(TARGET).nacp $(TARGET).elf

#---------------------------------------------------------------------------------
else
.PHONY:	all

DEPENDS	:=	$(OFILES:.o=.d)

#---------------------------------------------------------------------------------
# main targets
#---------------------------------------------------------------------------------
all	:	$(OUTPUT).nro

$(OUTPUT).nro	:	$(OUTPUT).elf $(OUTPUT).nacp

$(OUTPUT).elf	:	$(OFILES)

-include $(DEPENDS)

#---------------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------------
