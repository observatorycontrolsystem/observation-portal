import Vue from 'vue';
import Tools from './tools.vue';

new Vue({
  el: '#app',
  render: function(h){
    return h(Tools);
  }
});
