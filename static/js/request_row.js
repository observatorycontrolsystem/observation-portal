import $ from 'jquery';
import moment from 'moment';
import {datetimeFormat} from './utils.js';

import { getThumbnail, getLatestFrame, downloadAll } from './archive.js';

$('.downloadall').click(function(){
  downloadAll($(this).data('requestid'));
});

$('.tt').tooltip();

$(document).ready(function() {
  $('.thumbnail-small').each(function(idx, elem) {
    getLatestFrame($(elem).data('request'), function(frame) {
      if (!frame) {
        $(elem).prev().show().html('Waiting on data to become available');
        $('button[data-requestid="' + $(elem).data('request') +'"]').prop('disabled', true);        
      } else {
        $(elem).fadeOut(200);
        $(elem).attr('alt', frame.filename);
        $(elem).attr('title', frame.filename);
        $(elem).prev().show().html('<center><span class="fa fa-spinner fa-spin"></span></center>');
        getThumbnail(frame.id, 75, function(data) {
          if (data.error) {
            $(elem).prev().html(data.error);
          } else {
            $(elem).attr('src', data.url).show();
            $(elem).prev().hide();
          }
        });
      }
    });
  });

  $('.pending-details').each(function() {
    let that = $(this);
    let requestId = $(this).data('request');
    $.getJSON('/api/requests/' + requestId + '/?exclude_canceled=true', function(data) {
      let content = '';
      if (data.length > 0) {
        data = data.reverse(); // get the latest non canceled block
        content = '<strong>' + data[0].site + '</strong> <br/>' +
          moment(data[0].start).format(datetimeFormat) +
          ' to ' + moment(data[0].end).format(datetimeFormat);
      } else {
        content = 'No scheduling information found';
      }
      that.html(content);
    });
  });
});
