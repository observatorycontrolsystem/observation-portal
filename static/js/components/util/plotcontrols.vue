<template>
  <b-container class="plot-controls">
      <b-button
        class="float-right"
        variant="transparent"
        id="zoom-in" 
        @click="zoomIn"
      >
        <i class="fas fa-search-plus"></i>
      </b-button>
      <b-button
        class="float-right"
        variant="transparent"
        id="zoom-in" 
        @click="zoomOut"
      >
        <i class="fas fa-search-minus"></i>
      </b-button>
  </b-container>
</template>
<script>
  export default {
    props: {
      zoomInPercent: {
        type:Number, 
        default:-0.2
      },
      zoomOutPercent: {
        type:Number, 
        default:0.2
      }
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
<style scoped>
  .plot-controls {
	  position: absolute;
    right: 0;
    /* Stays under modals but above its vis graph */
    z-index: 500;
}
</style>
