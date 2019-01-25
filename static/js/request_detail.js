import Vue from 'vue';
import $ from 'jquery';
import './request_row';
import App from './request_detail.vue';

import {cancelUserRequest} from './userrequest_header';

$('#cancelur').click(function(){
  cancelUserRequest($(this).data('id'));
});

new Vue({
  el: '#app',
  render: function(h){
    return h(App);
  }
});

