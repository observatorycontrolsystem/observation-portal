import Vue from 'vue';
import _ from 'lodash';
import $ from 'jquery';
import BootstrapVue from 'bootstrap-vue';
import 'bootstrap/dist/css/bootstrap.css';
import 'bootstrap-vue/dist/bootstrap-vue.css';

import { formatDate } from './utils.js';
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


function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = $.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}

$( document ).ajaxSend(
    function(event, request, settings) {
        console.log('beforeSend');
        console.log(settings);
        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
            var csrftoken = getCookie('csrftoken');
            request.setRequestHeader('X-CSRFToken', csrftoken);
        }
    });
