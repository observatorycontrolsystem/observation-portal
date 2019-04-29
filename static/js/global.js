import 'babel-polyfill';
import $ from 'jquery';
import 'bootstrap';

import { archiveAjaxSetup } from './archive.js';
import { csrfSafeMethod, getCookie } from './global.js';

archiveAjaxSetup();

// Make sure ajax POSTs get CSRF protection
$.ajaxSetup({
  beforeSend: function(xhr, settings) {
    if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
      var csrftoken = getCookie('csrftoken');
      xhr.setRequestHeader('X-CSRFToken', csrftoken);
    }
  }
});
