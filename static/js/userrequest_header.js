import $ from 'jquery';

export {cancelUserRequest};

function cancelUserRequest(id) {
  if(confirm('Cancel this request? This action cannot be undone')){
    $.ajax({
      type: 'POST',
      url: '/api/userrequests/' + id + '/cancel/',
      contentType: 'application/json',
    }).done(function(){
      window.location = '/userrequests/' + id + '/';
    }).fail(function(data){
      if(data.status == 429){
        alert('Too many cancel requests, your request to cancel has been throttled. Please contact support.');
      }else{
        alert(data.responseJSON.errors[0]);
      }
    });
  }
}
