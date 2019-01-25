<template>
  <div class="telescopeAvailability">
    {{ error }}
    <table class="availability_chart table table-bordered table-condensed" v-show="sortedTelescopes.length">
        <thead class="thead-default">
            <th>Telescope</th>
            <th v-for="dateLabel in dateLabels">{{ dateLabel }}</th>
        </thead>
        <tbody class="tbody-default">
            <tr v-for="telescope in sortedTelescopes">
                <td>{{ telescope | readableSiteName}}</td>
                <td v-for="availabilities in availabilityData[telescope]" :class="[availabilityToColor(availabilities[1])]">
                    {{ (availabilities[1] * 100).toFixed() }}
                </td>
            </tr>
        </tbody>
    </table>
    <p v-show="!sortedTelescopes.length && !error" class="text-center"><i class="fa fa-spin fa-spinner"></i></p>
  </div>
</template>
<script>
import _ from 'lodash';
import $ from 'jquery';

export default {
  name: 'app',
  data: function(){
    return {
      availabilityData: {},
      minDate:null,
      maxDate:null,
      dateLabels:[],
      sortedTelescopes:[],
      error: ''
    };
  },
  created: function(){
    var that = this;
    var endDate = new Date();
    var startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - 3);
    startDate.setHours(0);
    startDate.setMinutes(0);
    startDate.setSeconds(0);
    startDate.setMilliseconds(0);
    $.getJSON('/api/telescope_availability/?start=' + startDate.toISOString() + '&end=' + endDate.toISOString(),
      function(data){
        if(data === 'ConnectionError'){
          that.error = 'Unable to retrieve history';
          return;
        }
        that.availabilityData = data;
      }
    );
  },
  methods: {
    availabilityToColor: function(availability){
      if(availability > 0.75) return 'success';
      else if (availability > 0.25) return 'warning';
      return 'danger';
    }
  },
  watch: {
    availabilityData: function () {
      this.minDate = new Date(8640000000000000);
      this.maxDate = new Date(-8640000000000000);
      for (var telescope in this.availabilityData){
        if(this.availabilityData[telescope].length > 0){
          var firstDate = new Date(this.availabilityData[telescope][0][0]);
          if (firstDate < this.minDate){
            this.minDate = firstDate;
          }
          var lastDate = new Date(_.last(this.availabilityData[telescope])[0]);
          if (lastDate > this.maxDate){
            this.maxDate = lastDate;
          }
          this.sortedTelescopes.push(telescope);
        }
      }

      this.sortedTelescopes.sort();

      this.dateLabels = [];
      var currentDate = new Date(this.minDate);
      while(currentDate <= this.maxDate){
        var days_ago = Math.ceil((this.maxDate.getTime() - currentDate.getTime()) / (1000 * 3600 * 24));
        if(days_ago == 0) this.dateLabels.push('Today');
        else if(days_ago == 1) this.dateLabels.push('-' + days_ago + ' day');
        else this.dateLabels.push('-' + days_ago + ' days');
        currentDate.setDate(currentDate.getDate() + 1);
      }
    }
  },
};
</script>
