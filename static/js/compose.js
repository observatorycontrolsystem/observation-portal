import Vue from 'vue';
import _ from 'lodash';
import $ from 'jquery';
import BootstrapVue from 'bootstrap-vue';
import 'bootstrap/dist/css/bootstrap.css';
import 'bootstrap-vue/dist/bootstrap-vue.css';
import '../css/main.css'

import { formatDate } from './utils.js';
import { csrfSafeMethod, getCookie } from './utils.js';
import App from './compose.vue';

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

let vm = new Vue({
  el: '#app',
  render: function(h) {
    return h(App);
  }
});

export { vm };

$( document ).ajaxSend(
    function(event, request, settings) {
      if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
          var csrftoken = getCookie('csrftoken');
          request.setRequestHeader('X-CSRFToken', csrftoken);
      }
    });
