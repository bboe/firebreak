#include <getopt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static char *joined(int first, int argc, char **argv) {
    size_t length = 1;
    for (int i = first; i < argc; i++) {
        length += strlen(argv[i]) + 1;
    }
    char *command = calloc(length, 1);
    for (int i = first; i < argc; i++) {
        if (*command) {
            strcat(command, " ");
        }
        strcat(command, argv[i]);
    }
    return command;
}

static int uid_of(const char *user) {
    if (strcmp(user, "root") == 0) {
        return 0;
    }
    if (strcmp(user, "system") == 0) {
        return 1000;
    }
    if (strcmp(user, "shell") == 0) {
        return 2000;
    }
    return atoi(user);
}

static void usage(int status) {
    fputs("Usage: su [options] [-] [user [argument...]]\n", status ? stderr : stdout);
    exit(status);
}

int main(int argc, char **argv) {
    char line[256];
    int rooted = 0;
    FILE *props = fopen("/sim/run/props", "r");
    while (props && fgets(line, sizeof line, props)) {
        rooted |= strcmp(line, "sim.su=1\n") == 0;
    }
    if (!rooted) {
        fputs("/system/bin/sh: su: not found\n", stderr);
        return 127;
    }
    static struct option long_options[] = {
        {"command", required_argument, NULL, 'c'},
        {"context", required_argument, NULL, 'z'},
        {"help", no_argument, NULL, 'h'},
        {"login", no_argument, NULL, 'l'},
        {"mount-master", no_argument, NULL, 'M'},
        {"preserve-environment", no_argument, NULL, 'p'},
        {"shell", required_argument, NULL, 's'},
        {"version", no_argument, NULL, 'v'},
        {NULL, 0, NULL, 0},
    };
    for (int i = 0; i < argc; i++) {
        if (strcmp(argv[i], "-cn") == 0) {
            strcpy(argv[i], "-z");
        } else if (strcmp(argv[i], "-mm") == 0) {
            strcpy(argv[i], "-M");
        }
    }
    char *command = NULL;
    int option;
    opterr = 0;
    while ((option = getopt_long(argc, argv, ":c:hlmps:Vvuz:M", long_options, NULL)) != -1) {
        switch (option) {
        case 'c':
            command = joined(optind - 1, argc, argv);
            optind = argc;
            break;
        case 'h':
            usage(0);
            break;
        case 'V':
            puts("17300");
            return 0;
        case 'v':
            puts("17.3:MAGISKSU (topjohnwu)");
            return 0;
        case 'l':
        case 'm':
        case 'p':
        case 's':
        case 'z':
        case 'M':
            break;
        case 'u':
            fputc('\n', stderr);
            usage(2);
            break;
        case ':':
            fprintf(stderr, "su: option requires an argument -- %c\n", optopt);
            usage(2);
            break;
        default:
            if (optopt) {
                fprintf(stderr, "su: unknown option -- %c\n", optopt);
            } else {
                fprintf(stderr, "su: unknown option -- %s\n", argv[optind - 1] + 2);
            }
            usage(2);
        }
    }
    if (optind < argc && strcmp(argv[optind], "-") == 0) {
        optind++;
    }
    const char *user = optind < argc ? argv[optind] : NULL;
    int uid = user ? uid_of(user) : 0;
    if (setgid(uid) || setuid(uid)) {
        perror("su");
        return 1;
    }
    if (command) {
        execl("/sim/path/sh", "sh", "-c", command, (char *)0);
    } else {
        execl("/sim/path/sh", "sh", (char *)0);
    }
    perror("su");
    return 1;
}
