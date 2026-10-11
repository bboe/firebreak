FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55 AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bzip2 ca-certificates curl gcc libc6-dev make zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /busybox.tar.bz2 https://busybox.net/downloads/busybox-1.22.1.tar.bz2 \
    && curl -fsSL -o /pigz.tar.gz https://github.com/madler/pigz/archive/refs/tags/v2.2.5.tar.gz \
    && curl -fsSL -o /toybox.tar.gz https://landley.net/toybox/downloads/toybox-0.7.6.tar.gz \
    && curl -fsSL -o /zlib.tar.gz https://zlib.net/fossils/zlib-1.2.8.tar.gz \
    && printf '%s\n' \
        'ae0b029d0a9e4dd71a077a790840e496dd838998e4571b87b60fed7462b6678b  /busybox.tar.bz2' \
        'c08ca41a00f9f1140a5cb9f90cb20189e81d219f63267f51f3fb1bca71e03abd  /pigz.tar.gz' \
        'e2c9643ebc2bcdec4d8f8db25d0b428dbe0928f7b730052dbbd25db47fb9db95  /toybox.tar.gz' \
        '36658cb768a54c1d4dec43c3116c27ed893e88b02ecfcb44f2166f9c0b7f2a0d  /zlib.tar.gz' \
        | sha256sum -c \
    && tar -C / -xjf /busybox.tar.bz2 && tar -C / -xzf /pigz.tar.gz && tar -C / -xzf /toybox.tar.gz \
    && tar -C / -xzf /zlib.tar.gz
RUN printf '#include <time.h>\nstatic inline int stime(const time_t *t) { struct timespec s = {*t, 0}; return clock_settime(CLOCK_REALTIME, &s); }\n' > /stime.h \
    && cd /busybox-1.22.1 && make defconfig >/dev/null \
    && sed -i 's|^CONFIG_EXTRA_CFLAGS=.*|CONFIG_EXTRA_CFLAGS="-include /stime.h"|' .config \
    && for name in FEATURE_HAVE_RPC FEATURE_INETD_RPC FEATURE_MOUNT_NFS; do \
        sed -i "s/^CONFIG_$name=y/# CONFIG_$name is not set/" .config; \
    done \
    && make -j8 >/dev/null 2>&1
RUN cd /pigz-2.2.5 && make >/dev/null 2>&1
RUN cd /toybox-0.7.6 && make defconfig >/dev/null \
    && for name in DD EXPR GUNZIP GZIP TOYBOX_LIBZ TR ZCAT; do \
        sed -i "s/^# CONFIG_$name is not set/CONFIG_$name=y/" .config; \
        grep -q "^CONFIG_$name=y" .config || echo "CONFIG_$name=y" >> .config; \
    done \
    && yes '' | make oldconfig >/dev/null && make -j8 >/dev/null 2>&1
RUN cd /zlib-1.2.8 && ./configure --static >/dev/null && make minigzip >/dev/null 2>&1
COPY su.c /su.c
RUN gcc -O2 -o /su /su.c

FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cpio e2fsprogs gdisk mksh original-awk python3 python3-fusepy unzip \
        util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /busybox-1.22.1/busybox /pigz-2.2.5/pigz /toybox-0.7.6/toybox /su /opt/dot/
COPY --from=build /zlib-1.2.8/minigzip /opt/dot/gzip
RUN chmod 4755 /opt/dot/su && printf 'ro.build.product=biscuit\n' > /default.prop
COPY device/ /sim/bin/
COPY flavours/ /sim/manifests/
RUN chmod 755 /sim/bin/* && /sim/bin/sim-flavours
CMD ["sleep", "infinity"]
