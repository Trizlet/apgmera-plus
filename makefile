
CU_COMPILER=nvcc

CU_FLAGS=-c --std=c++11
COMPILER_FLAGS=-c -Wall -Wextra -pedantic -O3 -pthread -g
LD_FLAGS=-pthread

ifdef USE_MINGW
PLATFORM=$(shell uname -s)
ifneq (, $(findstring CYGWIN, $(PLATFORM))$(findstring MINGW, $(PLATFORM)))
CPP_COMPILER=x86_64-w64-mingw32-g++
C_COMPILER=x86_64-w64-mingw32-gcc
else
CPP_COMPILER=x86_64-w64-mingw32-g++-posix
C_COMPILER=x86_64-w64-mingw32-gcc-posix
endif
EXTRA_LIBS=-static -lwinpthread -lwsock32 -lws2_32 -static-libstdc++
else
COMPILER_FLAGS += -march=native
CPP_COMPILER=g++
C_COMPILER=gcc
endif

LINKER=$(CPP_COMPILER)

CPP_FLAGS=$(COMPILER_FLAGS) --std=c++11
C_FLAGS=$(COMPILER_FLAGS) -fomit-frame-pointer

CPP_SOURCES=main.cpp includes/md5.cpp includes/happyhttp.cpp

ifdef USE_GPU
LD_FLAGS=
CU_SOURCES=includes/gpusrc.cu
LINKER=$(CU_COMPILER)
else
COMPILER_FLAGS += -flto=auto
LD_FLAGS += -flto=auto
endif

ifndef USE_MINGW
ifeq ($(shell pkg-config --exists libcurl 2>/dev/null && echo yes),yes)
COMPILER_FLAGS += -DUSE_CURL $(shell pkg-config --cflags libcurl)
EXTRA_LIBS += $(shell pkg-config --libs libcurl)
endif
endif

OBJECTS=$(CPP_SOURCES:.cpp=.o) $(C_SOURCES:.c=.o) $(CU_SOURCES:.cu=.o)
OBJECTS_PROFILE=$(OBJECTS:.o=.op)
EXECUTABLE=apgluxe
EXECUTABLE_PROFILE=$(EXECUTABLE)-profile
THREADS=4

PROF_MERGER=true

ifdef PROFILE_APGLUXE
PROFILE_DEPENDENCIES=$(EXECUTABLE_PROFILE)
PROFILE_ARGS=-fprofile-use -fprofile-correction
ifeq "$(shell $(CPP_COMPILER) --version | grep -o clang)" "clang"
PROF_MERGER=$(shell bash -c 'compgen -c' | grep 'llvm-profdata' | sort -V | tail -n 1)
else
CPP_FLAGS += -funsafe-loop-optimizations -Wunsafe-loop-optimizations
endif
ifeq "$(PROF_MERGER)" ""
PROF_MERGER=xcrun llvm-profdata
endif
endif

.SUFFIXES: .cpp .cu .o .op

# Compile:
all: $(CPP_SOURCES) $(PROFILE_DEPENDENCIES) $(EXECUTABLE)
	true
	true                                                oo o
	true                                                oo ooo
	true                                                      o
	true                                                oo ooo
	true                                                 o o
	true                                                 o o
	true                                                  o

# Clean the build environment by deleting any object files:
clean: 
	sh -c 'rm -f apgluxe *.o */*.o *.op */*.op *.gdca */*.gcda *.profraw *.profdata || true'
	echo Clean done

$(EXECUTABLE): $(OBJECTS)
	$(LINKER) $(LD_FLAGS) $(PROFILE_ARGS) $(OBJECTS) $(EXTRA_LIBS) -o $@

.cpp.o:
	$(CPP_COMPILER) $(CPP_FLAGS) $(PROFILE_ARGS) $< -o $@

.cu.o:
	$(CU_COMPILER) $(CU_FLAGS) $< -o $@

# Making profiler executable to do further optimization:

$(EXECUTABLE_PROFILE): $(OBJECTS_PROFILE)
	true        Using merger $(PROF_MERGER)
	$(LINKER) $(LD_FLAGS) -fprofile-generate $(OBJECTS_PROFILE) $(EXTRA_LIBS) -o $@
	true        Generating optimization profile, this may take some time...
	./$@ -n 100000 -t 1 -s l_kEwHfF3ArtPb -p $(THREADS) -i 1 -v 0
	$(PROF_MERGER) merge -o default.profdata *.profraw
	true        done!

.cpp.op:
	$(CPP_COMPILER) $(CPP_FLAGS) -fprofile-generate $< -o $@
