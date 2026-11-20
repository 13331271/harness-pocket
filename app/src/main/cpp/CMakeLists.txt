# Native-only Android PTY targets; derived from the MIT-licensed DSH Mobile build.
# Optional proprietary Linux container and graphics server are intentionally absent.
cmake_minimum_required(VERSION 3.22.1)
project(dshpty C)

add_library(dshpty SHARED dsh_pty.c)

# Android packaging includes lib*.so artifacts. This executable is extracted by
# the existing native runtime installer as engine/bin/dsh_pty_exec.
add_executable(dsh_pty_exec dsh_pty_exec.c)
set_target_properties(dsh_pty_exec PROPERTIES OUTPUT_NAME "libdsh_pty_exec.so")

# Keep both targets suitable for 16KB-page Android kernels with NDK r26 as well
# as later NDKs; retain the upstream explicit alignment contract.
target_link_options(dshpty PRIVATE "-Wl,-z,max-page-size=16384")
target_link_options(dsh_pty_exec PRIVATE "-Wl,-z,max-page-size=16384")

target_link_libraries(dshpty log)
