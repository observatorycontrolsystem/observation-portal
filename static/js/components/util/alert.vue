<template>
  <div v-if="show" class="alert alert-dismissiable" :class="alertclass" role="alert">
    <slot></slot>
    <button class="close" v-on:click="show = false"><i class="fa fa-times"></i></button>
  </div>
</template>

<script>
  export default {
    props: ['alertclass'],
    data: function(){
      return {show: true}
    },
    created: function(){
      let that = this;
      setTimeout(function(){
        that.show = false;
      }, 10000)
    }
  };
</script>
