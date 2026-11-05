struct fake_device {
 unsigned host,head,count;
 spi_transaction_t *items[2];
 unsigned state[2]; /* 1 queued, 2 active, 3 done */
 uint64_t finished[2];
};
static struct fake_device devices[2];
static uint64_t irq_service_until;
static void queue_tick(unsigned cycles){irq_service_until=(irq_service_until>now?irq_service_until:now)+cycles;}
esp_err_t spi_bus_initialize(spi_host_device_t h,const spi_bus_config_t*c,int d){(void)h;(void)c;(void)d;return ESP_OK;}
esp_err_t spi_bus_free(spi_host_device_t h){(void)h;return ESP_OK;}
esp_err_t spi_bus_add_device(spi_host_device_t h,const spi_device_interface_config_t*c,spi_device_handle_t*d){assert(c->queue_size==2);*d=&devices[h-2];(*d)->host=h-2;return ESP_OK;}
esp_err_t spi_bus_remove_device(spi_device_handle_t d){assert(!d->count);return ESP_OK;}
esp_err_t spi_device_get_actual_freq(spi_device_handle_t d,int*f){(void)d;*f=80000;return ESP_OK;}
static void start_wire(struct fake_device*d,unsigned slot,uint64_t at){
 unsigned h=d->host;d->state[slot]=2;
 uint64_t wire=((uint64_t)S3_PP_TX_BYTES*8+80)*3/(h?4:8);
 wire_done[h]=at+wire;irq_at[h]=wire_done[h];
 if(last_submit[h]&&at-last_submit[h]>max_submit_gap[h])max_submit_gap[h]=at-last_submit[h];last_submit[h]=at;
}
esp_err_t spi_device_queue_trans(spi_device_handle_t d,spi_transaction_t*t,int wait){
 assert(!wait&&d->count<2);unsigned slot=(d->head+d->count)&1;
 bool active=false;for(unsigned i=0;i<d->count;i++)active|=d->state[(d->head+i)&1]==2;
 d->items[slot]=t;d->state[slot]=1;d->count++;
 if(!active){unsigned h=d->host;unsigned fee=launches[h]++?COST_IRQ_START:COST_IRQ_FIRST;queue_tick(fee);joint_charge(SPI_IRQ,fee);start_wire(d,slot,now);}
 return ESP_OK;
}
esp_err_t spi_device_get_trans_result(spi_device_handle_t d,spi_transaction_t**t,int wait){
 assert(!wait);if(!d->count||d->state[d->head]!=3)return ESP_ERR_TIMEOUT;
 unsigned h=d->host;uint64_t age=now-d->finished[d->head];if(age>max_wire_to_reap[h])max_wire_to_reap[h]=age;
 *t=d->items[d->head];d->state[d->head]=0;d->head^=1;d->count--;return ESP_OK;
}
static void queue_irq(unsigned h){
 struct fake_device*d=&devices[h];bool found=false;
 for(unsigned i=0;i<d->count;i++){unsigned k=(d->head+i)&1;if(d->state[k]==2){d->state[k]=3;d->finished[k]=now;found=true;break;}}
 assert(found);uint64_t start=irq_service_until>now?irq_service_until:now;uint64_t charge=COST_IRQ_COMPLETE;unsigned events=1;irq_at[h]=UINT64_MAX;
 for(unsigned i=0;i<d->count;i++){unsigned k=(d->head+i)&1;if(d->state[k]==1){charge+=COST_IRQ_START;events++;launches[h]++;start_wire(d,k,start+charge);break;}}
 irq_service_until=start+charge;
 ready[0]+=charge;charged[0][SPI_IRQ]+=charge;counts[0][SPI_IRQ]+=events;interrupts[0]+=charge;
}
static esp_err_t s3_pp_spi_reap(s3_pp_transfer*x){
 struct fake_device*d=x->device;bool done=d->count&&d->state[d->head]==3;
 /* No running-command guard for queue depth2. Empty SDK query is 209*1.1. */
 joint_charge(done?REAP_DONE:REAP_RUNNING,done?COST_REAP_DONE:230);
 if(!done&&d->count&&d->state[d->head]==3)joint_charge(REAP_DONE,COST_REAP_DONE-230);
 uint64_t seq=x->sequences[x->head];const uint8_t*data=x->transactions[x->head].tx_buffer;
 esp_err_t rc=s3_raw_queue_reap(x);
 if(rc==ESP_OK){check_payload(seq,data);transfers_done[d->host]++;}return rc;
}
static esp_err_t s3_pp_spi_submit(s3_pp_transfer*x,s3_parallel_pack*p,s3_spi_port*port,unsigned epoch){
 (void)port;(void)epoch;
 bool available=p->submitted<p->published/S3_PP_TX_BYTES;
 joint_charge(available?SUBMIT_DONE:SUBMIT_EMPTY,available?COST_SUBMIT_DONE:COST_SUBMIT_EMPTY);
 return s3_raw_queue_submit(x);
}
