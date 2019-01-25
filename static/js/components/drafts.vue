<template>
  <table class="table table-striped">
    <thead>
      <tr>
        <td>Load</td><td>Title</td><td>Id</td><td>Author</td>
        <td>Proposal</td><td>Last Modified</td><td>Delete</td>
      </tr>
    </thead>
    <tbody>
      <tr v-show="drafts.length < 1">
        <td colspan="7">You have no draft observing requests.</td>
      </tr>
      <tr v-for="draft in drafts">
        <td><button class="btn btn-info" v-on:click="loadDraft(draft.id)"><i class="fa fa-download"></i></button></td>
        <td>{{ draft.title }}</td>
        <td>{{ draft.id }}</td>
        <td>{{ draft.author }}</td>
        <td>{{ draft.proposal }}</td>
        <td>{{ draft.modified | formatDate  }}</td>
        <td>
          <button class="btn btn-danger" v-on:click="deleteDraft(draft.id)">
            <i class="fa fa-trash"></i>
          </button>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<script>
import $ from 'jquery';
export default {
  props: ['tab'],
  data: function(){
    return {'drafts': []};
  },
  methods: {
    fetchDrafts: function(){
      var that = this;
      $.getJSON('/api/drafts/', function(data){
        that.drafts = data.results;
      });
    },
    loadDraft: function(id){
      this.$emit('loaddraft', id);
    },
    deleteDraft: function(id){
      if(confirm('Are you sure you want to delete this draft?')){
        var that = this;
        $.ajax({
          type: 'DELETE',
          url: '/api/drafts/' + id + '/'
        }).done(function(){
          that.fetchDrafts();
        });
      }
    }
  },
  watch: {
    tab: function(value){
      if(value === 3) this.fetchDrafts();
    }
  }
};
</script>
