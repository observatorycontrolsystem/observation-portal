import $ from 'jquery';
import './request_row';
import {cancelRequestGroup} from './requestgroup_header';

$('#cancelrg').click(function(){
  cancelRequestGroup($(this).data('id'));
});
