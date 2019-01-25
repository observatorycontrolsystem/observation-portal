<template>
  <div class="plot_controls">
    <button type="button" id="zoom-in" class="btn btn-default" v-on:click="zoomIn" >
      <span class="glyphicon glyphicon-zoom-in" aria-hidden="true"></span>
    </button>
    <button type="button" id="zoom-out" class="btn btn-default" v-on:click="zoomOut" >
      <span class="glyphicon glyphicon-zoom-out" aria-hidden="true"></span>
    </button>
  </div>
</template>
<script>

import 'vue-style-loader!../../../css/plot_style.css';

export default {
  props: {
    zoomInPercent:{type:Number, default:-0.2},
    zoomOutPercent:{type:Number, default:0.2}
  },
  methods: {
    zoomIn: function(){
      this.$emit('plotZoom', this.zoomInPercent);
    },
    zoomOut: function(value){
      this.$emit('plotZoom', this.zoomOutPercent);
    }
  }
};
</script>
