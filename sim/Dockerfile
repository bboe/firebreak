FROM ubuntu:24.04
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        busybox cpio e2fsprogs gdisk python3 toybox util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/toybox && mv /usr/bin/toybox /opt/toybox/toybox
RUN for flavour in recovery-busybox recovery-toybox device; do \
        mkdir -p /sim/flavours/$flavour && ln -s /usr/bin/busybox /sim/flavours/$flavour/dd; \
    done \
    && ln -s /opt/toybox/toybox /sim/flavours/recovery-toybox/toybox \
    && ln -s /opt/toybox/toybox /sim/flavours/device/toybox
RUN printf 'ro.build.product=biscuit\n' > /default.prop
COPY device/ /sim/bin/
RUN chmod 755 /sim/bin/*
CMD ["sleep", "infinity"]
