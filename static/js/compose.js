import Vue from 'vue';
import _ from 'lodash';
import $ from 'jquery';
import BootstrapVue from 'bootstrap-vue';
import 'bootstrap-vue/dist/bootstrap-vue.css';
import '../css/main.css'

import App from './compose.vue';
import { 
  addCsrfProtection,
  formatDate, 
  formatField, 
  getFieldDescription 
} from './utils.js';

$(document).ajaxSend(addCsrfProtection);

Vue.use(BootstrapVue);

Vue.mixin({
  computed: {
    _: function(){
      return _;
    }
  }
});

Vue.filter('formatDate', function(value) {
  return formatDate(value);
});

Vue.filter('formatField', function(value) {
  return formatField(value);
});

Vue.filter('getFieldDescription', function(value) {
  return getFieldDescription(value);
});

let vm = new Vue({
  el: '#app',
  render: function(h) {
    return h(App);
  }
});

export { vm };
