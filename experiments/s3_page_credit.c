#include "s3_page_credit.h"
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#else
#define IRAM_ATTR
#endif
#define SEQUENCE_MASK UINT32_C(0xfffff)

int s3_credit_init_window(s3_page_credit *c,unsigned epoch,uint32_t first,unsigned window)
{
    if(!c||!epoch||epoch>UINT16_MAX||first>SEQUENCE_MASK||(window!=2&&window!=4&&window!=8))return S3_RANGE;
    *c=(s3_page_credit){.next=first,.retired=first,.epoch=(uint16_t)epoch,.window=(uint8_t)window};
    return S3_OK;
}

int s3_credit_init(s3_page_credit *c,unsigned epoch,uint32_t first)
{
    return s3_credit_init_window(c,epoch,first,2);
}

int IRAM_ATTR s3_credit_status(s3_page_credit *c,const uint8_t p[16])
{
    if(!c||!p)return S3_RANGE;
    if(c->poisoned)return S3_STALE;
    for(unsigned i=0;i<8;++i)if((unsigned)(p[i]^p[i+8])!=255){
        c->poisoned=true;return S3_STALE;
    }
    unsigned epoch=((unsigned)p[2]<<8)|p[3];
    uint32_t frontier=((uint32_t)p[4]<<12)|((uint32_t)p[5]<<4)|(p[6]>>4);
    if(p[0]!=0xc7||p[1]!=0xa1||epoch!=c->epoch||(p[6]&15)!=c->window||p[7]){
        c->poisoned=true;return S3_STALE;
    }
    uint32_t progress=(frontier-c->retired)&SEQUENCE_MASK;
    uint32_t outstanding=(c->next-c->retired)&SEQUENCE_MASK;
    if(progress>outstanding){c->poisoned=true;return S3_STALE;}
    c->retired=frontier;c->synced=true;
    return S3_OK;
}

int IRAM_ATTR s3_credit_reserve(s3_page_credit *c,unsigned pages,uint32_t *first)
{
    if(!c||!first||!pages||pages>c->window)return S3_RANGE;
    if(c->poisoned)return S3_STALE;
    if(!c->synced)return S3_BUSY;
    uint32_t outstanding=(c->next-c->retired)&SEQUENCE_MASK;
    if(outstanding>c->window){c->poisoned=true;return S3_STALE;}
    if(pages>c->window-outstanding)return S3_BUSY;
    *first=c->next;c->next=(c->next+pages)&SEQUENCE_MASK;
    return S3_OK;
}

void IRAM_ATTR s3_credit_poison(s3_page_credit *c)
{
    if(c)c->poisoned=true;
}
