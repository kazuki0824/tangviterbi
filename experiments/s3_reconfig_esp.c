#include "s3_reconfig_esp.h"
#ifdef ESP_PLATFORM
#include "driver/gpio.h"
#include "esp_rom_sys.h"
bool s3_reconfig_esp_open(s3_reconfig_esp *s,bool (*quiescent)(void *),void *ctx)
{
 if(!s||s->opened||!quiescent||!quiescent(ctx))return false;
 // Preload RELEASE before enabling the output driver to avoid a low glitch.
 if(gpio_set_level(40,1)!=ESP_OK)return false;
 gpio_config_t cfg={.pin_bit_mask=UINT64_C(1)<<40,.mode=GPIO_MODE_OUTPUT_OD,
  .pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
 if(gpio_config(&cfg)!=ESP_OK)return false;
 *s=(s3_reconfig_esp){quiescent,ctx,true};return true;
}
bool s3_reconfig_esp_pulse(void *ctx)
{
 s3_reconfig_esp*s=ctx;
 if(!s||!s->opened||!s->quiescent(s->context))return false;
 if(gpio_set_level(40,0)!=ESP_OK)return false;
 // UG290's minimum RECONFIG_N low time is 25 ns. The ROM busy delay holds
 // it for 5 us; interrupts may lengthen the pulse. No maximum is specified.
 esp_rom_delay_us(5);
 return gpio_set_level(40,1)==ESP_OK;
}
#endif
