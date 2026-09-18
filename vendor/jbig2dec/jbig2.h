/* Minimal public API header for linking against system libjbig2dec. */
#ifndef CAJ2PDF_JBIG2_H
#define CAJ2PDF_JBIG2_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct _Jbig2Allocator Jbig2Allocator;
typedef struct _Jbig2Ctx Jbig2Ctx;
typedef struct _Jbig2GlobalCtx Jbig2GlobalCtx;

typedef enum {
    JBIG2_SEVERITY_DEBUG,
    JBIG2_SEVERITY_INFO,
    JBIG2_SEVERITY_WARNING,
    JBIG2_SEVERITY_FATAL
} Jbig2Severity;

typedef enum {
    JBIG2_OPTIONS_EMBEDDED = 1
} Jbig2Options;

typedef int (*Jbig2ErrorCallback)(void *data, const char *msg, Jbig2Severity severity, int32_t seg_idx);

struct _Jbig2Allocator {
    void *(*alloc)(Jbig2Allocator *allocator, size_t size);
    void (*free)(Jbig2Allocator *allocator, void *p);
    void *(*realloc)(Jbig2Allocator *allocator, void *p, size_t size);
};

typedef struct _Jbig2Image {
    uint32_t width;
    uint32_t height;
    uint32_t stride;
    uint8_t *data;
    int refcount;
} Jbig2Image;

Jbig2Ctx *jbig2_ctx_new(Jbig2Allocator *allocator, Jbig2Options options,
                        Jbig2GlobalCtx *global_ctx,
                        Jbig2ErrorCallback error_callback,
                        void *error_callback_data);
void jbig2_ctx_free(Jbig2Ctx *ctx);
int jbig2_data_in(Jbig2Ctx *ctx, const unsigned char *data, size_t size);
int jbig2_complete_page(Jbig2Ctx *ctx);
Jbig2Image *jbig2_page_out(Jbig2Ctx *ctx);
void jbig2_release_page(Jbig2Ctx *ctx, Jbig2Image *image);

#ifdef __cplusplus
}
#endif
#endif
