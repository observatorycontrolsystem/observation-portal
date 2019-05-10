import Vue from 'vue';
import Tools from './tools.vue';
import BootstrapVue from 'bootstrap-vue';
import 'bootstrap/dist/css/bootstrap.css';
import 'bootstrap-vue/dist/bootstrap-vue.css';
import '../css/main.css';

Vue.use(BootstrapVue);

new Vue({
  el: '#app',
  render: function(h) {
    return h(Tools);
  }
});
