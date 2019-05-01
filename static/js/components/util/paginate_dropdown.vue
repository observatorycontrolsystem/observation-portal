<template>
  <select 
    name="paginate_by" 
    class="form-control" 
    id="per_page" 
    @change="onChange($event)"        
  >
    <option value="5">Show: 5</option>
    <option value="10">Show: 10</option>
    <option value="20" selected>Show: 20</option>
    <option value="50">Show: 50</option>
    <option value="100">Show: 100</option>
  </select>
</template>
<script>
  import $ from 'jquery';
  export default {
    name: 'app',
    mounted: function(){
      var url = new URL(window.location.href);
      var value = "20";
      if(url.searchParams.get('paginate_by')){
        value = url.searchParams.get('paginate_by');
      }
      $('#per_page').val(value);
    },
    methods: {
      onChange: function(event) {
        var url = new URL(window.location.href);
        url.searchParams.set('paginate_by', event.target.value);
        window.location = url;
      }
    }
  };
</script>