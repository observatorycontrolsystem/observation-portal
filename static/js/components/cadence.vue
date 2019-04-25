<template>
  <div class="cadencetimeline"></div>
</template>
<script>
  import vis from 'vis';

  export default {
    props: [
      'data'
    ],
    data: function() {
      return {
        options: {
          moment: function(date) {
            return vis.moment(date).utc();
          }
        },
        items: this.toVis
      };
    },
    computed:{
      toVis: function() {
        let visData = [];
        for (let r in this.data) {
          let request = this.data[r];
          visData.push({
              id: r, 
              content: '' + (Number(r) + 1), 
              start: request.windows[0].start, 
              end: request.windows[0].end,
              style: 'border-radius: 5px;'
            });
        }
        return new vis.DataSet(visData);
      }
    },
    watch: {
      data: function() {
        this.timeline.setItems(this.toVis);
        this.timeline.fit();
      }
    },
    mounted: function(){
      this.timeline = new vis.Timeline(this.$el, this.items, this.options);
    }
  };
</script>
<style scoped>
  @import '~vis/dist/vis.css';
</style>
