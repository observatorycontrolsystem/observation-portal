import $ from 'jquery';
import './request_row';
import {cancelUserRequest} from './userrequest_header';

$('#cancelur').click(function(){
  cancelUserRequest($(this).data('id'));
});
